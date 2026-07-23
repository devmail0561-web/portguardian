"""Tests for core.alerts — AlertRule matching and AlertEngine evaluation."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.alerts import AlertRule, AlertEngine, Alert
from core.ports import ConnectionInfo


def _conn(
    port=80,
    protocol="tcp",
    status="LISTEN",
    process="nginx",
    user="root",
    pid=100,
):
    return ConnectionInfo(
        protocol=protocol,
        local_addr="0.0.0.0",
        local_port=port,
        remote_addr="",
        remote_port=0,
        status=status,
        pid=pid,
        process_name=process,
        username=user,
        fd=0,
    )


class TestAlertRuleMatching:
    """Tests for AlertRule.matches()."""

    def test_port_exact_match(self):
        rule = AlertRule(name="r", severity="warning", port=22)
        assert rule.matches(_conn(port=22))
        assert not rule.matches(_conn(port=80))

    def test_port_lt(self):
        rule = AlertRule(name="r", severity="warning", port_lt=1024)
        assert rule.matches(_conn(port=80))
        assert not rule.matches(_conn(port=1024))
        assert not rule.matches(_conn(port=8080))

    def test_port_gt(self):
        rule = AlertRule(name="r", severity="info", port_gt=1024)
        assert rule.matches(_conn(port=8080))
        assert not rule.matches(_conn(port=1024))
        assert not rule.matches(_conn(port=80))

    def test_protocol_match(self):
        rule = AlertRule(name="r", severity="info", protocol="udp")
        assert rule.matches(_conn(protocol="udp"))
        assert not rule.matches(_conn(protocol="tcp"))

    def test_status_match(self):
        rule = AlertRule(name="r", severity="info", status="ESTABLISHED")
        assert rule.matches(_conn(status="ESTABLISHED"))
        assert not rule.matches(_conn(status="LISTEN"))

    def test_process_exact(self):
        rule = AlertRule(name="r", severity="warning", process="bash")
        assert rule.matches(_conn(process="bash"))
        assert not rule.matches(_conn(process="sshd"))

    def test_process_substring(self):
        rule = AlertRule(name="r", severity="info", process="*python")
        assert rule.matches(_conn(process="python3"))
        assert rule.matches(_conn(process="mypython"))
        assert not rule.matches(_conn(process="nginx"))

    def test_process_not(self):
        rule = AlertRule(name="r", severity="critical", port=22, process_not="sshd")
        assert rule.matches(_conn(port=22, process="bash"))
        assert not rule.matches(_conn(port=22, process="sshd"))

    def test_user_match(self):
        rule = AlertRule(name="r", severity="info", user="www-data")
        assert rule.matches(_conn(user="www-data"))
        assert not rule.matches(_conn(user="root"))

    def test_user_not(self):
        rule = AlertRule(name="r", severity="warning", port_lt=1024, user_not="root")
        assert rule.matches(_conn(port=80, user="nobody"))
        assert not rule.matches(_conn(port=80, user="root"))

    def test_multiple_conditions_all_must_match(self):
        rule = AlertRule(name="r", severity="critical", port=22, status="LISTEN", process_not="sshd")
        # All conditions met
        assert rule.matches(_conn(port=22, status="LISTEN", process="bash"))
        # Port doesn't match
        assert not rule.matches(_conn(port=80, status="LISTEN", process="bash"))
        # Process matches the exclusion
        assert not rule.matches(_conn(port=22, status="LISTEN", process="sshd"))

    def test_no_conditions_always_matches(self):
        rule = AlertRule(name="r", severity="info")
        assert rule.matches(_conn())
        assert rule.matches(_conn(port=9999, protocol="udp", status="NONE"))

    def test_to_dict_excludes_none_fields(self):
        rule = AlertRule(name="ssh", severity="critical", port=22)
        d = rule.to_dict()
        assert "port" in d
        assert "port_lt" not in d
        assert "process" not in d

    def test_from_dict_roundtrip(self):
        rule = AlertRule(name="test", severity="warning", port=443, process_not="nginx")
        d = rule.to_dict()
        rule2 = AlertRule.from_dict(d)
        assert rule2.name == "test"
        assert rule2.port == 443
        assert rule2.process_not == "nginx"
        assert rule2.process is None


class TestAlertEngineEvaluation:
    """Tests for AlertEngine.evaluate()."""

    def test_rule_fires_on_matching_connection(self):
        engine = AlertEngine.__new__(AlertEngine)
        engine._rules = [
            AlertRule(name="ssh-check", severity="critical", port=22, process_not="sshd")
        ]
        conns = [_conn(port=22, process="bash")]
        alerts = engine.evaluate(conns)
        assert len(alerts) == 1
        assert alerts[0].rule_name == "ssh-check"
        assert alerts[0].severity == "critical"

    def test_rule_does_not_fire_when_no_match(self):
        engine = AlertEngine.__new__(AlertEngine)
        engine._rules = [
            AlertRule(name="ssh-check", severity="critical", port=22, process_not="sshd")
        ]
        conns = [_conn(port=22, process="sshd")]
        alerts = engine.evaluate(conns)
        assert len(alerts) == 0

    def test_multiple_rules_multiple_alerts(self):
        engine = AlertEngine.__new__(AlertEngine)
        engine._rules = [
            AlertRule(name="r1", severity="warning", port=80),
            AlertRule(name="r2", severity="info", port=80),
        ]
        conns = [_conn(port=80)]
        alerts = engine.evaluate(conns)
        assert len(alerts) == 2

    def test_multiple_connections_each_evaluated(self):
        engine = AlertEngine.__new__(AlertEngine)
        engine._rules = [AlertRule(name="r", severity="info", port=22)]
        conns = [_conn(port=22), _conn(port=22, pid=200), _conn(port=80)]
        alerts = engine.evaluate(conns)
        assert len(alerts) == 2

    def test_empty_connections_no_alerts(self):
        engine = AlertEngine.__new__(AlertEngine)
        engine._rules = [AlertRule(name="r", severity="warning", port=22)]
        assert engine.evaluate([]) == []

    def test_empty_rules_no_alerts(self):
        engine = AlertEngine.__new__(AlertEngine)
        engine._rules = []
        assert engine.evaluate([_conn(port=22)]) == []

    def test_alert_message_contains_rule_name(self):
        engine = AlertEngine.__new__(AlertEngine)
        engine._rules = [AlertRule(name="my-rule", severity="warning")]
        alerts = engine.evaluate([_conn()])
        assert "my-rule" in alerts[0].message

    def test_add_and_remove_rule(self, tmp_path):
        with patch("core.alerts.RULES_FILE", tmp_path / "rules.json"):
            engine = AlertEngine.__new__(AlertEngine)
            engine._rules = []
            rule = AlertRule(name="new", severity="info", port=9090)
            engine.add_rule(rule)
            assert len(engine._rules) == 1
            removed = engine.remove_rule("new")
            assert removed
            assert len(engine._rules) == 0

    def test_remove_nonexistent_rule_returns_false(self, tmp_path):
        with patch("core.alerts.RULES_FILE", tmp_path / "rules.json"):
            engine = AlertEngine.__new__(AlertEngine)
            engine._rules = []
            assert not engine.remove_rule("ghost")

    def test_save_and_reload_rules(self, tmp_path):
        rules_file = tmp_path / "rules.json"
        with patch("core.alerts.RULES_FILE", rules_file):
            engine = AlertEngine.__new__(AlertEngine)
            engine._rules = [AlertRule(name="saved", severity="critical", port=8080)]
            engine.save_rules()

            engine2 = AlertEngine.__new__(AlertEngine)
            engine2._rules = []
            engine2._load_rules()
            assert len(engine2._rules) == 1
            assert engine2._rules[0].name == "saved"


class TestAlertDataclass:
    """Tests for Alert dataclass."""

    def test_auto_message_generation(self):
        conn = _conn(port=22, process="bash", user="root", pid=999)
        alert = Alert(rule_name="ssh", severity="critical", connection=conn)
        assert "ssh" in alert.message
        assert "22" in alert.message
        assert "bash" in alert.message

    def test_custom_message_preserved(self):
        conn = _conn()
        alert = Alert(rule_name="r", severity="info", connection=conn, message="custom msg")
        assert alert.message == "custom msg"
