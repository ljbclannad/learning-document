# 合并K个升序链表

类型：[[算法/10-堆与优先队列/堆与优先队列详解|堆与优先队列]] · 难度：高难度 · LeetCode 23（Hard / 困难）

题目来源：[LeetCode 23：合并K个升序链表](https://leetcode.com/problems/merge-k-sorted-lists/)。以下题意为中文概述，示例和解法用于学习；完整平台约束以原题为准。

## 题意与输入输出

合并 k 条升序无环链表并返回升序链表，复用节点。假设各输入链表不共享节点。

示例：`[1→4, 2→3, 空链] → 1→2→3→4`。

## 从直觉到算法

每条链只将当前头部放入最小堆。堆顶小于等于所有可见头部，也小于等于各头部之后的节点，所以它就是全局最小未输出节点；取出后放入其后继，保持不变量。

## 关键步骤推演

初始堆中 1、2，取 1 后补 4；取 2 后补 3；再取 3、4，完成合并。

## Java 实现

以下是可独立编译的完整 `Solution` 类，基线 Java 17；没有 `main` 入口。链表、树的辅助节点定义包含在类中，提交平台时应替换为平台提供的节点类型。除正文另有约定外，引用参数非 null，输入满足题目结构约束；实现未做全部非法输入校验。

```java
import java.util.PriorityQueue;

class Solution {
    static class ListNode {
        int val;
        ListNode next;
        ListNode(int val) { this.val = val; }
    }

    public ListNode mergeKLists(ListNode[] lists) {
        PriorityQueue<ListNode> heap = new PriorityQueue<>((a, b) -> Integer.compare(a.val, b.val));
        for (ListNode head : lists) if (head != null) heap.offer(head);
        ListNode dummy = new ListNode(0), tail = dummy;
        while (!heap.isEmpty()) {
            ListNode node = heap.poll();
            if (node.next != null) heap.offer(node.next);
            tail.next = node; tail = node;
        }
        tail.next = null;
        return dummy.next;
    }
}
```

## 复杂度与输入影响

N 为节点总数，时间 O(N log(k+1))，堆空间 O(k)，结果复用原节点。

## 边界用例与验证

比较节点值用 Integer.compare。共享尾部会导致同一节点重复入堆甚至成环，因此输入契约要求节点不共享。空链只跳过，不能向堆插入 null。

以下断言片段应放在同一个 `Solution` 类的静态测试入口中，`s` 是 `new Solution()`，`check` 在条件为假时抛出 `AssertionError`。测试用的 `Arrays`、`Collections`、`HashSet`、`List` 等类型需要显式导入；统一运行方式见导航中的验证说明。

```java
ListNode a=new ListNode(1),b=new ListNode(4),c=new ListNode(2),d=new ListNode(3);a.next=b;c.next=d;
ListNode r=s.mergeKLists(new ListNode[]{a,c,null});check(r==a && a.next==c && c.next==d && d.next==b && b.next==null);
check(s.mergeKLists(new ListNode[0])==null);check(s.mergeKLists(new ListNode[]{null})==null);
```

## 面试追问与变式

分治两两合并也能达到 O(N log k)；需要稳定区分同值不同来源时，可增加来源编号作为第二排序键。
