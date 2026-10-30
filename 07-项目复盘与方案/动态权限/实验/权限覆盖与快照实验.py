from dataclasses import dataclass


def effective(role_actions, override, enabled):
    base = role_actions if override is None else override
    return frozenset(base) & frozenset(enabled)


def can_manage(actions, action, actor_org, allowed_depts,
               target_org, target_dept, active=True):
    return (
        active
        and actor_org is not None
        and target_dept is not None
        and action in actions
        and actor_org == target_org
        and target_dept in allowed_depts
    )


@dataclass(frozen=True)
class Snapshot:
    version: int
    actions: frozenset


class CacheModel:
    def __init__(self, current_version):
        self.current_version = current_version
        self.snapshot = None

    def publish_version(self, version):
        self.current_version = max(self.current_version, version)

    def install(self, candidate):
        if candidate.version != self.current_version:
            return False
        self.snapshot = candidate
        return True

    def read(self):
        if self.snapshot is None:
            return None
        if self.snapshot.version != self.current_version:
            return None
        return self.snapshot


role = {"user:read", "user:update"}
assert effective(role, None, role) == frozenset(role)
assert effective(role, set(), role) == frozenset()
assert effective(role, {"user:read"}, role) == frozenset({"user:read"})
assert effective(role, None, {"user:read"}) == frozenset({"user:read"})
assert can_manage(role, "user:update", "H1", {"D1"}, "H1", "D1")
assert not can_manage(role, "user:update", "H1", {"D1"}, "H2", "D1")
assert not can_manage(role, "user:update", "H1", {"D1"}, "H1", "D2")
assert not can_manage(role, "user:update", "H1", set(), "H1", "D1")
assert not can_manage(role, "user:update", "H1", {"D1"}, "H1", "D1", False)
assert not can_manage({"user:read"}, "user:update", "H1", {"D1"}, "H1", "D1")

cache = CacheModel(10)
old = Snapshot(10, frozenset(role))
assert cache.install(old)
cache.publish_version(11)
assert cache.read() is None
assert not cache.install(old)
new = Snapshot(11, frozenset({"user:read"}))
assert cache.install(new)
cache.publish_version(10)              # 模拟旧通知晚到
assert cache.read() == new
cache.snapshot = None                 # 删除快照，水位仍保留
assert not cache.install(old)
assert cache.read() is None
assert cache.install(new)
