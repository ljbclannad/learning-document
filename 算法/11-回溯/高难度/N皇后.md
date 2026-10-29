# N皇后

类型：[[算法/11-回溯/回溯详解|回溯]] · 难度：高难度 · LeetCode 51（Hard / 困难）

题目来源：[LeetCode 51：N皇后](https://leetcode.com/problems/n-queens/)。以下题意为中文概述，示例和解法用于学习；完整平台约束以原题为准。

## 题意与输入输出

在 n×n 棋盘放 n 个皇后，任意两个不得同列、同行或同对角线，返回全部棋盘方案。n≥1。

示例：`n=4 有 2 解，其中一解列位置为 [1,3,0,2]（从 0 编号）`。

## 从直觉到算法

每行放一个皇后，自动满足不同行。用列占用、row-col+n-1 和 row+col 两组对角线占用数组做 O(1) 冲突检查，合法才进入下一行。

## 关键步骤推演

选第 0 行第 1 列，下一行避开列 1 和对角线，选择列 3；之后选列 0、2，形成一个完整解。回退时释放占用，再探索其他选择。

## Java 实现

以下是可独立编译的完整 `Solution` 类，基线 Java 17；没有 `main` 入口。链表、树的辅助节点定义包含在类中，提交平台时应替换为平台提供的节点类型。除正文另有约定外，引用参数非 null，输入满足题目结构约束；实现未做全部非法输入校验。

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

class Solution {
    public List<List<String>> solveNQueens(int n) {
        if (n < 1) throw new IllegalArgumentException("n 必须为正数");
        List<List<String>> result = new ArrayList<>();
        search(0, n, new int[n], new boolean[n], new boolean[2*n-1], new boolean[2*n-1], result);
        return result;
    }
    private void search(int row, int n, int[] position, boolean[] cols,
                        boolean[] descending, boolean[] ascending, List<List<String>> result) {
        if (row == n) {
            List<String> board = new ArrayList<>();
            for (int col : position) {
                char[] line = new char[n]; Arrays.fill(line, '.'); line[col] = 'Q';
                board.add(new String(line));
            }
            result.add(board); return;
        }
        for (int col = 0; col < n; col++) {
            int d = row - col + n - 1, a = row + col;
            if (cols[col] || descending[d] || ascending[a]) continue;
            position[row] = col; cols[col] = descending[d] = ascending[a] = true;
            search(row + 1, n, position, cols, descending, ascending, result);
            cols[col] = descending[d] = ascending[a] = false;
        }
    }
}
```

## 复杂度与输入影响

保守搜索上界 O(n·n!)，每个完整方案构造棋盘还需 O(n²)；若解数为 S，总时间可写 O(n·n!+S·n²)。工作空间 O(n)，结果 O(S·n²)。

## 边界用例与验证

对角线索引范围都是 0～2n-2。保存棋盘字符串而不是可变占用数组。n=2、3 无解，n=1 有一个解。

以下断言片段应放在同一个 `Solution` 类的静态测试入口中，`s` 是 `new Solution()`，`check` 在条件为假时抛出 `AssertionError`。测试用的 `Arrays`、`Collections`、`HashSet`、`List` 等类型需要显式导入；统一运行方式见导航中的验证说明。

```java
check(s.solveNQueens(4).size()==2);check(s.solveNQueens(1).equals(Arrays.asList(Arrays.asList("Q"))));
check(s.solveNQueens(2).isEmpty());check(s.solveNQueens(3).isEmpty());check(s.solveNQueens(8).size()==92);
```

## 面试追问与变式

只求数量时可省掉棋盘构造；位运算能加快冲突检测，但位宽限制和位移溢出必须明确。
