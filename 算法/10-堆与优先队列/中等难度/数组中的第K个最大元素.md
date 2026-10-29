# 数组中的第K个最大元素

类型：[[算法/10-堆与优先队列/堆与优先队列详解|堆与优先队列]] · 难度：中等难度 · LeetCode 215（Medium / 中等）

题目来源：[LeetCode 215：数组中的第K个最大元素](https://leetcode.com/problems/kth-largest-element-in-an-array/)。以下题意为中文概述，示例和解法用于学习；完整平台约束以原题为准。

## 题意与输入输出

返回数组按降序排序后第 k 个元素，重复元素也占位置，1≤k≤n。

示例：`nums=[5,1,4,4], k=2 → 4`。

## 从直觉到算法

维护至多 k 个最大候选，使用最小堆让最弱候选在堆顶。每次加入新数后若超出 k，就移除最小值，因此扫描后堆中恰好是最大的 k 个元素。

## 关键步骤推演

k=2 时先有 [1,5]，加入 4 后移出 1；加入第二个 4 后移出一个 4，保留 4、5，堆顶为 4。

## Java 实现

以下是可独立编译的完整 `Solution` 类，基线 Java 17；没有 `main` 入口。链表、树的辅助节点定义包含在类中，提交平台时应替换为平台提供的节点类型。除正文另有约定外，引用参数非 null，输入满足题目结构约束；实现未做全部非法输入校验。

```java
import java.util.PriorityQueue;

class Solution {
    public int findKthLargest(int[] nums, int k) {
        if (k < 1 || k > nums.length) throw new IllegalArgumentException("k 超出范围");
        PriorityQueue<Integer> heap = new PriorityQueue<>();
        for (int value : nums) {
            heap.offer(value);
            if (heap.size() > k) heap.poll();
        }
        return heap.peek();
    }
}
```

## 复杂度与输入影响

时间 O(n log(k+1))，空间 O(k)，不修改输入。

## 边界用例与验证

不能使用 Set 去重；k=1 等价于最大值，k=n 等价于最小值。非法 k 明确抛异常。

以下断言片段应放在同一个 `Solution` 类的静态测试入口中，`s` 是 `new Solution()`，`check` 在条件为假时抛出 `AssertionError`。测试用的 `Arrays`、`Collections`、`HashSet`、`List` 等类型需要显式导入；统一运行方式见导航中的验证说明。

```java
check(s.findKthLargest(new int[]{5,1,4,4},2)==4);check(s.findKthLargest(new int[]{5,1,4,4},3)==4);
check(s.findKthLargest(new int[]{-1,-3},1)==-1);check(s.findKthLargest(new int[]{-1,-3},2)==-3);
```

## 面试追问与变式

快速选择平均 O(n) 但通常修改数组，极端选轴会退化；数据流输入时为什么固定大小堆更自然？
