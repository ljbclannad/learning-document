# 子数组最大平均数I

类型：[[算法/03-滑动窗口/滑动窗口详解|滑动窗口]] · 难度：低难度 · LeetCode 643（Easy / 简单）

题目来源：[LeetCode 643：子数组最大平均数I](https://leetcode.com/problems/maximum-average-subarray-i/)。以下题意为中文概述，示例和解法用于学习；完整平台约束以原题为准。

## 题意与输入输出

给定数组和 1≤k≤n，找出长度恰为 k 的连续子数组的最大平均数。

示例：`nums=[2, -1, 5, 0], k=2 → 2.5`。

## 从直觉到算法

每个窗口重新求和需 O(nk)。相邻窗口仅差一个离开元素和一个加入元素，所以维护 sum，每步减去 nums[right-k] 再加 nums[right]。

## 关键步骤推演

初始 [2,-1] 的和为 1；右移为 [-1,5]，和为 4；再右移为 [5,0]，和为 5，最大平均数是 5/2。

## Java 实现

以下是可独立编译的完整 `Solution` 类，基线 Java 17；没有 `main` 入口。链表、树的辅助节点定义包含在类中，提交平台时应替换为平台提供的节点类型。除正文另有约定外，引用参数非 null，输入满足题目结构约束；实现未做全部非法输入校验。

```java
class Solution {
    public double findMaxAverage(int[] nums, int k) {
        if (k < 1 || k > nums.length) throw new IllegalArgumentException("窗口长度非法");
        long sum = 0;
        for (int i = 0; i < k; i++) sum += nums[i];
        long best = sum;
        for (int right = k; right < nums.length; right++) {
            sum += (long) nums[right] - nums[right - k];
            best = Math.max(best, sum);
        }
        return (double) best / k;
    }
}
```

## 复杂度与输入影响

时间 O(n)，额外空间 O(1)。sum 用 long，最终转 double 除法。

## 边界用例与验证

全负数时 best 必须从第一个真实窗口初始化，不能设零。k=1 与 k=n 都应覆盖。

以下断言片段应放在同一个 `Solution` 类的静态测试入口中，`s` 是 `new Solution()`，`check` 在条件为假时抛出 `AssertionError`。测试用的 `Arrays`、`Collections`、`HashSet`、`List` 等类型需要显式导入；统一运行方式见导航中的验证说明。

```java
check(s.findMaxAverage(new int[]{2,-1,5,0},2)==2.5);
check(s.findMaxAverage(new int[]{-5,-3},1)==-3.0);
check(s.findMaxAverage(new int[]{2,4},2)==3.0);
```

## 面试追问与变式

若 k 不固定且要求长度至少 k，不能简单取同一套更新规则；先分析目标的单调性和是否需要二分答案。
