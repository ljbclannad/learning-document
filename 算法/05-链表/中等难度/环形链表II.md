# 环形链表II

类型：[[算法/05-链表/链表详解|链表]] · 难度：中等难度 · LeetCode 142（Medium / 中等）

题目来源：[LeetCode 142：环形链表II](https://leetcode.com/problems/linked-list-cycle-ii/)。以下题意为中文概述，示例和解法用于学习；完整平台约束以原题为准。

## 题意与输入输出

若单链表存在环，返回环入口节点；否则返回 null。不能修改链表。

示例：`1→2→3→4，4.next 指向节点 2 → 返回节点 2`。

## 从直觉到算法

快指针每次两步，慢指针每次一步。相遇后，将一个指针移回头部，二者改为同步一步，下一次相遇即入口。设头到入口 a，入口到相遇点 b，环长 L，则慢指针走了 a+b，快慢路程差是整圈，故 a+b 为 L 的倍数；从相遇点再走 a 步恰到入口。

## 关键步骤推演

示例中快慢最终在环内相遇；一个回头，一个留在相遇点，同速走过头到入口的距离后共同到节点 2。判断应使用引用 ==。

## Java 实现

以下是可独立编译的完整 `Solution` 类，基线 Java 17；没有 `main` 入口。链表、树的辅助节点定义包含在类中，提交平台时应替换为平台提供的节点类型。除正文另有约定外，引用参数非 null，输入满足题目结构约束；实现未做全部非法输入校验。

```java
class Solution {
    static class ListNode {
        int val;
        ListNode next;
        ListNode(int val) { this.val = val; }
    }

    public ListNode detectCycle(ListNode head) {
        ListNode slow = head, fast = head;
        while (fast != null && fast.next != null) {
            slow = slow.next;
            fast = fast.next.next;
            if (slow == fast) {
                ListNode fromHead = head;
                while (fromHead != slow) { fromHead = fromHead.next; slow = slow.next; }
                return fromHead;
            }
        }
        return null;
    }
}
```

## 复杂度与输入影响

时间 O(n)，额外空间 O(1)，不改链表。

## 边界用例与验证

访问 fast.next.next 前必须检查 fast 与 fast.next。入口可能是头节点，单节点自环也合法。值相等不能代表同一节点。

以下断言片段应放在同一个 `Solution` 类的静态测试入口中，`s` 是 `new Solution()`，`check` 在条件为假时抛出 `AssertionError`。测试用的 `Arrays`、`Collections`、`HashSet`、`List` 等类型需要显式导入；统一运行方式见导航中的验证说明。

```java
ListNode a=new ListNode(1),b=new ListNode(2),c=new ListNode(3),d=new ListNode(4); a.next=b;b.next=c;c.next=d;d.next=b;
check(s.detectCycle(a)==b); d.next=null; check(s.detectCycle(a)==null);
a.next=a; check(s.detectCycle(a)==a); check(s.detectCycle(null)==null);
```

## 面试追问与变式

如何计算环长？相遇后固定一个指针，另一个绕一圈计步；再进一步求入口前长度。
