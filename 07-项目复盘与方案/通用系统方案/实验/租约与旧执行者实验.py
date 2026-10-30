import unittest


class LeaseModel:
    def __init__(self):
        self.token = 0
        self.until = 0
        self.state = "PENDING"

    def claim(self, now, duration):
        if duration <= 0:
            raise ValueError("租约必须为正")
        if self.state == "DONE":
            return None
        if self.state == "PROCESSING" and now < self.until:
            return None
        self.token += 1
        self.until = now + duration
        self.state = "PROCESSING"
        return self.token

    def unsafe_finish(self, token):
        self.state = "DONE"  # 反例：无视本次身份和租约
        return True

    def finish(self, token, now):
        if (self.state != "PROCESSING" or token != self.token
                or now >= self.until):
            return False
        self.state = "DONE"
        return True


class LeaseProtocolTest(unittest.TestCase):
    def test_stale_owner_regression(self):
        broken = LeaseModel()
        old = broken.claim(0, 5)
        broken.claim(6, 5)
        self.assertTrue(broken.unsafe_finish(old))  # 成功复现错误放行
        fixed = LeaseModel()
        old = fixed.claim(0, 5)
        self.assertIsNone(fixed.claim(1, 5))
        new = fixed.claim(6, 5)
        self.assertFalse(fixed.finish(old, 7))
        self.assertEqual(fixed.state, "PROCESSING")
        self.assertTrue(fixed.finish(new, 7))
        self.assertIsNone(fixed.claim(20, 5))

    def test_expired_without_reclaim(self):
        model = LeaseModel()
        token = model.claim(0, 5)
        self.assertFalse(model.finish(token, 5))

    def test_local_fence_cannot_undo_external_effect(self):
        model = LeaseModel()
        old = model.claim(0, 5)
        new = model.claim(6, 5)
        external_effects = []
        external_effects.append("旧请求已在外部执行")
        self.assertFalse(model.finish(old, 7))
        external_effects.append("新请求再次在外部执行")
        self.assertTrue(model.finish(new, 7))
        self.assertEqual(len(external_effects), 2)


if __name__ == "__main__":
    unittest.main()
