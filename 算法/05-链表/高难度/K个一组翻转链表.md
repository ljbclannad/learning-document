# K个一组翻转链表

类型：[[算法/05-链表/链表详解|链表]] · 难度：高难度 · LeetCode 25（Hard / 困难）

题目来源：[LeetCode 25：K个一组翻转链表](https://leetcode.com/problems/reverse-nodes-in-k-group/)。以下题意为中文概述，示例和解法用于学习；完整平台约束以原题为准。

## 题意与输入输出

将无环链表每 k 个节点作为一组反转；末尾不足 k 个保持原序。k 为正整数，不通过交换节点值完成。

示例：`1→2→3→4→5，k=2 → 2→1→4→3→5`。

## 从直觉到算法

虚拟头节点连接已完成部分。每组先向后查满 k 个节点，再反转至该组后继 groupNext 为止，最后把组前驱接到新头。先检查长度，避免不足一组也被反转。

## 关键步骤推演

第一组为 1、2，后继是 3；让反转初始 prev=3，得到 2→1→3。原组头 1 变为尾部，作为下一组前驱；末尾 5 不足两节点保持不变。

## Java 实现

以下是可独立编译的完整 `Solution` 类，基线 Java 17；没有 `main` 入口。链表、树的辅助节点定义包含在类中，提交平台时应替换为平台提供的节点类型。除正文另有约定外，引用参数非 null，输入满足题目结构约束；实现未做全部非法输入校验。

```java
class Solution {
    static class ListNode {
        int val;
        ListNode next;
        ListNode(int val) { this.val = val; }
    }

    public ListNode reverseKGroup(ListNode head, int k) {
        if (k < 1) throw new IllegalArgumentException("k 必须为正数");
        ListNode dummy = new ListNode(0); dummy.next = head;
        ListNode before = dummy;
        while (true) {
            ListNode kth = before;
            for (int i = 0; i < k && kth != null; i++) kth = kth.next;
            if (kth == null) break;
            ListNode groupNext = kth.next, current = before.next, prev = groupNext;
            while (current != groupNext) {
                ListNode next = current.next;
                current.next = prev; prev = current; current = next;
            }
            ListNode oldHead = before.next;
            before.next = kth;
            before = oldHead;
        }
        return dummy.next;
    }
}
```

## 复杂度与输入影响

时间 O(n)，每个节点被查找和反转常数次；额外空间 O(1)。修改原节点的 next。

## 边界用例与验证

必须保存原组头，因为它将成为下一次的前驱。k=1 无需修改；k>n 返回原链表。

以下断言片段应放在同一个 `Solution` 类的静态测试入口中，`s` 是 `new Solution()`，`check` 在条件为假时抛出 `AssertionError`。测试用的 `Arrays`、`Collections`、`HashSet`、`List` 等类型需要显式导入；统一运行方式见导航中的验证说明。

```java
ListNode a=new ListNode(1),b=new ListNode(2),c=new ListNode(3),d=new ListNode(4),e=new ListNode(5);a.next=b;b.next=c;c.next=d;d.next=e;
check(s.reverseKGroup(a,2)==b);check(b.next==a && a.next==d && d.next==c && c.next==e && e.next==null);
check(s.reverseKGroup(e,3)==e);check(s.reverseKGroup(e,1)==e);check(s.reverseKGroup(null,2)==null);
```

## 面试追问与变式

若不足 k 个也要反转，应修改哪一处终止策略？递归按组处理时最大栈深是多少？
