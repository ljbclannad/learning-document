# 和为K的子数组

类型：[[算法/04-前缀和/前缀和详解|前缀和]] · 难度：中等难度 · LeetCode 560（Medium / 中等）

题目来源：[LeetCode 560：和为K的子数组](https://leetcode.com/problems/subarray-sum-equals-k/)。以下题意为中文概述，示例和解法用于学习；完整平台约束以原题为准。

## 题意与输入输出

统计和等于 k 的非空连续子数组数量，数组可能包含负数和零。

示例：`nums=[2,-2,2], k=0 → 2`。

## 从直觉到算法

区间和为 k 等价于两个前缀之差为 k。扫描当前前缀 sum 时，累加历史前缀 sum-k 的出现次数，再把 sum 的次数加一。必须保存次数，因为相同前缀可能对应多个不同起点。

## 关键步骤推演

先放入 0→1；前缀 2 无匹配；前缀 0 匹配初始 0，答案 1；前缀 2 匹配第一次的 2，答案 2。

## Java 实现

以下是可独立编译的完整 `Solution` 类，基线 Java 17；没有 `main` 入口。链表、树的辅助节点定义包含在类中，提交平台时应替换为平台提供的节点类型。除正文另有约定外，引用参数非 null，输入满足题目结构约束；实现未做全部非法输入校验。

```java
import java.util.HashMap;
import java.util.Map;

class Solution {
    public long subarraySum(int[] nums, long k) {
        Map<Long, Long> frequency = new HashMap<>();
        frequency.put(0L, 1L);
        long sum = 0, answer = 0;
        for (int value : nums) {
            sum += value;
            answer += frequency.getOrDefault(sum - k, 0L);
            frequency.merge(sum, 1L, Long::sum);
        }
        return answer;
    }
}
```

## 复杂度与输入影响

平均时间 O(n)，空间 O(n)。前缀与答案使用 long，支持超出平台 int 结果的教学输入。

## 边界用例与验证

[0,0,0]、k=0 的结果为 6；若用 Set 只能知道存在，无法正确计数。负数让固定方向的和比较失去单调性。

以下断言片段应放在同一个 `Solution` 类的静态测试入口中，`s` 是 `new Solution()`，`check` 在条件为假时抛出 `AssertionError`。测试用的 `Arrays`、`Collections`、`HashSet`、`List` 等类型需要显式导入；统一运行方式见导航中的验证说明。

```java
check(s.subarraySum(new int[]{2,-2,2},0)==2); check(s.subarraySum(new int[]{0,0,0},0)==6);
check(s.subarraySum(new int[]{1,2,3},3)==2); check(s.subarraySum(new int[0],0)==0);
```

## 面试追问与变式

若要求最长长度，Map 应保存某前缀最早出现的下标；若要求最短长度，保存策略为什么要改变？
