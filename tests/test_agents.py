"""Each architecture really does what it claims (assignment section 'Testing')."""
import copy
import random

import pytest

from agents import AGENT_CLASSES, Brain, make_agent
from agents.contextual import ContextualAgent
from agents.hierarchical import HierarchicalAgent
from agents.learning import LearningAgent, state_of
from agents.model_based import ModelBasedReflexAgent
from agents.simple_reflex import SimpleReflexAgent
from agents.utility_based import WEIGHTS, UtilityBasedAgent
from engine.environment import DeliveryEnvironment
from engine.metrics import execute_runs, summarize
from engine.scenarios import SCENARIOS, get_scenario


def decide(agent, sc):
    agent.reset()
    for p in DeliveryEnvironment(sc).percepts():
        agent.perceive(p)
    return agent.decide()


@pytest.fixture(scope="module")
def brain():
    b = Brain()
    b.train(1500, 42)
    return b


def test_all_agents_decide_in_all_situations(brain):
    for sc in SCENARIOS:
        for cls in AGENT_CLASSES:
            a = make_agent(cls.key, brain)
            d = decide(a, sc)
            assert d.route in "ABCD" and d.reason
            phases = [s.phase for s in a.trace.steps]
            assert phases[0] == "observe" and phases[-1] == "decide"


def test_simple_reflex_has_no_memory():
    sc = get_scenario(2)
    p_old, p_new = DeliveryEnvironment(sc).percepts()
    a = SimpleReflexAgent()
    a.perceive(p_old)
    a.perceive(p_new)
    assert a.percept is p_new and not hasattr(a, "state")
    b = SimpleReflexAgent()
    b.perceive(p_new)                        # seeing only the latest percept gives the same decision
    assert a.decide().route == b.decide().route == "C"   # cannot see that B (offline sensor) is light


def test_simple_reflex_rules():
    d = decide(SimpleReflexAgent(), get_scenario(1))
    assert d.route == "A" and "R2" in d.reason
    d = decide(SimpleReflexAgent(), get_scenario(3))
    assert d.route == "B" and "R3" in d.reason        # R1 removed flooded C, R3 picked B


def test_model_based_updates_and_uses_internal_state():
    a = ModelBasedReflexAgent()
    sc = get_scenario(2)
    p_old, p_new = DeliveryEnvironment(sc).percepts()
    a.perceive(p_old)
    before = copy.deepcopy(a.state)
    a.perceive(p_new)
    assert a.state["traffic"]["B"]["level"] == "light" and a.state["traffic"]["B"]["source"] == "remembered"
    assert before != a.state
    assert a.decide().route == "B"
    a.reset()
    assert a.state["traffic"] == {}                     # reset clears the memory


def test_model_based_models_flooding():
    a = ModelBasedReflexAgent()
    decide(a, get_scenario(3))
    assert a.state["flooded"] == ["C"] and a.state["current_route"] == "D"


def test_goal_based_tests_the_goal():
    a = make_agent("goal_based")
    d = decide(a, get_scenario(2))
    assert d.route == "C" and d.predicted_total_min <= 30          # first plan (by distance) that satisfies the goal
    assert decide(make_agent("goal_based"), get_scenario(3)).route == "D"


def test_goal_based_fallback_when_goal_is_impossible():
    sc = copy.deepcopy(get_scenario(3))
    sc.order.deadline_min = 10
    a = make_agent("goal_based")
    d = decide(a, sc)
    assert d.notify_customer and any(s.kind == "goal-fail" for s in a.trace.steps)
    assert d.predicted_total_min > 10                                 # never pretends the goal is met


def test_utility_values_match_the_formula():
    a = UtilityBasedAgent()
    d = decide(a, get_scenario(3))
    rows = [s for s in a.trace.steps if s.kind == "utility"][-1].data["rows"]
    for r in rows:
        assert r["utility"] == pytest.approx(sum(WEIGHTS[k] * r["scores"][k] for k in WEIGHTS), abs=0.02)
        assert 0 <= min(r["scores"].values()) and max(r["scores"].values()) <= 100
    assert d.route == max(rows, key=lambda r: r["utility"])["route"]


def test_learning_updates_from_rewards():
    b = Brain()
    s, a = "clear|normal|AN BN CN DN", "B"
    u1 = b.update(s, a, 6.0)
    assert u1["q_old"] == 0 and u1["q_new"] == pytest.approx(6.0)        # alpha = 1/1
    u2 = b.update(s, a, 2.0)
    assert u2["q_new"] == pytest.approx(4.0)                              # running mean of 6 and 2


def test_learning_improves_and_learns_the_best_route(brain):
    s = brain.summary()
    assert s["last_avg"] > s["first_avg"]
    for sc in SCENARIOS:
        learned = decide(LearningAgent(brain), sc).route
        best = max("ABCD", key=lambda r: summarize(execute_runs(sc, r, 300, 7))["reward"])
        assert learned == best, (sc.id, learned, best)


def test_learning_is_reproducible_and_untrained_agent_knows_nothing():
    b1, b2 = Brain(), Brain()
    b1.train(300, 3)
    b2.train(300, 3)
    assert b1.q == b2.q
    a = LearningAgent(Brain())
    decide(a, get_scenario(1))
    assert any(s.title == "No experience for this state" for s in a.trace.steps)


def test_learning_run_does_not_change_the_shared_brain(brain):
    before = copy.deepcopy(brain.q)
    a = LearningAgent(brain)
    sc = get_scenario(3)
    d = decide(a, sc)
    a.learn(DeliveryEnvironment(sc).execute(d.route, random.Random(1)))
    assert brain.q == before and a.brain.q != before


def test_hierarchical_respects_task_dependencies():
    a = HierarchicalAgent()
    decide(a, get_scenario(3))
    done = [t["id"] for t in a.task_list() if t["status"] == "completed"]
    assert done == ["accept", "check_order", "traffic", "weather", "select"]
    order = [l.split(":")[0] for l in a.log if l.endswith("completed")]
    assert order.index("Select route") > order.index("Evaluate traffic") and order.index("Select route") > order.index("Check weather")
    with pytest.raises(RuntimeError):
        a._run("confirm", lambda: "")                                    # dependencies not met yet
    a.on_execution("pickup", {"prep": 5})
    a.on_execution("delivered", {"route": "D", "travel": 16, "total": 21, "on_time": True, "late": 0})
    assert all(t["status"] == "completed" for t in a.task_list())


def test_contextual_switches_strategy_with_context():
    classes = []
    for sc in SCENARIOS:
        a = ContextualAgent()
        decide(a, sc)
        classes.append([s for s in a.trace.steps if s.kind == "context"][-1].data["class"])
    assert classes == ["calm", "congested", "storm_urgent"]


def test_contextual_differs_from_utility_and_reflex_where_context_matters():
    sc = get_scenario(3)
    assert decide(ContextualAgent(), sc).route == "D"
    assert decide(UtilityBasedAgent(), sc).route == "B"
    assert decide(SimpleReflexAgent(), sc).route == "B"


def test_every_agent_explains_every_route(brain):
    for sc in SCENARIOS:
        for cls in AGENT_CLASSES:
            a = make_agent(cls.key, brain)
            d = decide(a, sc)
            notes = a.route_notes
            assert set(notes) == set("ABCD"), (cls.key, sc.id)
            assert [r for r, n in notes.items() if n["status"] == "chosen"] == [d.route]
            assert all(n["reason"] and n["status"] in ("chosen", "rejected", "not considered") for n in notes.values())


def test_rulebook_and_used_rules(brain):
    for cls in AGENT_CLASSES:
        ids = [r["id"] for sec in cls.RULEBOOK for r in sec["rules"]]
        assert ids and len(ids) == len(set(ids)), cls.key
        for sc in SCENARIOS:
            a = make_agent(cls.key, brain)
            decide(a, sc)
            assert a.fired and set(a.fired) <= set(ids), (cls.key, sc.id, a.fired)
    contexts = []
    for sc in SCENARIOS:
        a = ContextualAgent()
        decide(a, sc)
        contexts.append([r for r in a.fired if r.startswith("C")])
    assert contexts == [["C5"], ["C3"], ["C1"]]
