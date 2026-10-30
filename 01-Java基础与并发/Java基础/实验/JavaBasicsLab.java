import java.io.IOException;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;

/** Java 17 本地机制实验，不连接数据库、网络或外部业务服务。 */
public final class JavaBasicsLab {
    private static int checks;

    private static void check(boolean condition, String message) {
        checks++;
        if (!condition) throw new AssertionError(message);
    }

    @FunctionalInterface
    interface CheckedAction { void run() throws Exception; }

    private static <T extends Throwable> T expect(Class<T> type, CheckedAction action) {
        checks++;
        try {
            action.run();
        } catch (Throwable failure) {
            if (type.isInstance(failure)) return type.cast(failure);
            throw new AssertionError("异常类型不符合预期：" + type.getName(), failure);
        }
        throw new AssertionError("未抛出预期异常：" + type.getName());
    }

    public static class Parent {
        String select(Object value) { return "父类Object"; }
        public String inherited() { return "继承方法"; }
    }

    static final class Child extends Parent {
        @Override String select(Object value) { return "子类Object"; }
        String select(String value) { return "子类String"; }
    }

    private static void replace(List<String> input) {
        input.add("共享修改");
        input = new ArrayList<>();
        input.add("仅局部引用");
    }

    private static void basics() {
        Parent parent = new Child();
        check(parent.select("输入").equals("子类Object"), "先按静态类型重载，再按实例重写");
        check(new Child().select("输入").equals("子类String"), "子类静态类型能选择String重载");
        List<String> items = new ArrayList<>();
        replace(items);
        check(items.equals(List.of("共享修改")), "修改共享对象与重绑局部引用不同");
        String original = "hello";
        check(original.concat("") == original, "空拼接不保证创建新实例");
        check(original.concat("!").equals("hello!") && original.equals("hello"), "原字符串不变");
    }

    static <T> void copy(List<? extends T> source, List<? super T> target) {
        for (T item : source) target.add(item);
    }

    interface Reader<T> { T read(); }
    static final class TextReader implements Reader<String> {
        @Override public String read() { return "正文"; }
    }

    // 故意制造堆污染，仅此方法抑制警告，以便观察读取端失败。
    @SuppressWarnings({"rawtypes", "unchecked"})
    private static void pollute(List<String> values) {
        List raw = values;
        raw.add(42);
    }

    private static void generics() {
        List<Number> numbers = new ArrayList<>();
        copy(List.of(1, 2), numbers);
        check(numbers.equals(List.of(1, 2)), "Integer来源可以复制到Number目标");
        check(new ArrayList<String>().getClass() == new ArrayList<Integer>().getClass(), "实例Class相同");
        List<String> values = new ArrayList<>();
        pollute(values);
        expect(ClassCastException.class, () -> { String value = values.get(0); });
        Number[] array = new Integer[1];
        expect(ArrayStoreException.class, () -> array[0] = 1.5);
        check(Arrays.stream(TextReader.class.getDeclaredMethods()).anyMatch(Method::isBridge), "存在桥接方法");
        List<? extends Number> view = numbers;
        view.clear();
        check(numbers.isEmpty(), "extends通配符不代表不可修改");
    }

    record UserKey(String tenantId, String userId) {}
    record PermissionSnapshot(List<String> scopes) {
        PermissionSnapshot { scopes = List.copyOf(scopes); }
    }

    static final class MutableKey {
        int id;
        MutableKey(int id) { this.id = id; }
        @Override public boolean equals(Object other) {
            return other instanceof MutableKey key && id == key.id;
        }
        @Override public int hashCode() { return id; }
    }

    private static void equality() {
        Map<UserKey, String> users = new HashMap<>();
        users.put(new UserKey("甲", "1"), "旧值");
        users.put(new UserKey("甲", "1"), "新值");
        users.put(new UserKey("乙", "1"), "另一租户");
        check(users.size() == 2, "相同身份覆盖，不同租户隔离");
        check(users.get(new UserKey("甲", "1")).equals("新值"), "值对象可重新构造查询");
        Map<MutableKey, String> map = new HashMap<>();
        MutableKey key = new MutableKey(1);
        map.put(key, "值");
        key.id = 2;
        check(map.size() == 1 && map.get(key) == null, "修改哈希键导致查找失联");
        List<String> source = new ArrayList<>(List.of("read"));
        List<String> view = Collections.unmodifiableList(source);
        PermissionSnapshot snapshot = new PermissionSnapshot(source);
        source.add("write");
        check(view.size() == 2 && snapshot.scopes().size() == 1, "视图与结构快照不同");
        expect(UnsupportedOperationException.class, () -> snapshot.scopes().add("admin"));
        List<StringBuilder> mutableElements = new ArrayList<>();
        mutableElements.add(new StringBuilder("旧"));
        List<StringBuilder> shallowCopy = List.copyOf(mutableElements);
        mutableElements.get(0).append("新");
        check(shallowCopy.get(0).toString().equals("旧新"), "结构复制不复制可变元素");
        expect(NullPointerException.class, () -> List.copyOf(Arrays.asList("a", null)));
    }

    static final class Resource implements AutoCloseable {
        private final String name;
        private final List<String> events;
        Resource(String name, List<String> events) {
            this.name = name;
            this.events = events;
            events.add("打开" + name);
        }
        @Override public void close() throws IOException {
            events.add("关闭" + name);
            throw new IOException("关闭" + name);
        }
    }

    private static Resource failOpen() throws IOException { throw new IOException("初始化失败"); }

    @SuppressWarnings("try") // 资源无需在主体使用，实验验证初始化与关闭。
    private static void resources() {
        List<String> events = new ArrayList<>();
        IOException body = expect(IOException.class, () -> {
            try (Resource a = new Resource("A", events); Resource b = new Resource("B", events)) {
                throw new IOException("主体失败");
            }
        });
        check(body.getMessage().equals("主体失败"), "主体异常保留");
        check(events.equals(List.of("打开A", "打开B", "关闭B", "关闭A")), "资源反序关闭");
        check(Arrays.stream(body.getSuppressed()).map(Throwable::getMessage).toList()
                .equals(List.of("关闭B", "关闭A")), "关闭异常按顺序成为suppressed");
        events.clear();
        IOException opening = expect(IOException.class, () -> {
            try (Resource a = new Resource("A", events); Resource b = failOpen()) { }
        });
        check(opening.getMessage().equals("初始化失败"), "初始化异常保留");
        check(events.equals(List.of("打开A", "关闭A")), "只关闭已成功初始化的资源");
        check(opening.getSuppressed().length == 1, "初始化失败后保留关闭异常");
        events.clear();
        IOException closing = expect(IOException.class, () -> {
            try (Resource a = new Resource("A", events); Resource b = new Resource("B", events)) { }
        });
        check(closing.getMessage().equals("关闭B") && closing.getSuppressed()[0].getMessage().equals("关闭A"),
                "主体成功时第一个关闭异常成为主异常");
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface RuntimeTag {}
    @Target(ElementType.METHOD)
    @interface DefaultTag {}
    public static final class Service extends Parent {
        @RuntimeTag @DefaultTag
        public void fail() { throw new IllegalStateException("业务失败"); }
    }

    private static void reflection() throws Exception {
        Method method = Service.class.getMethod("fail");
        check(method.isAnnotationPresent(RuntimeTag.class), "运行时注解可见");
        check(!method.isAnnotationPresent(DefaultTag.class), "默认CLASS注解不可见");
        check(Service.class.getMethod("inherited").getName().equals("inherited"), "getMethod查找继承方法");
        expect(NoSuchMethodException.class, () -> Service.class.getDeclaredMethod("inherited"));
        InvocationTargetException wrapper = expect(InvocationTargetException.class,
                () -> method.invoke(new Service()));
        check(wrapper.getCause() instanceof IllegalStateException
                && wrapper.getCause().getMessage().equals("业务失败"), "业务异常保存在cause中");
    }

    private static boolean expired(Instant deadline, Clock clock) {
        return !clock.instant().isBefore(deadline);
    }

    private static void moneyAndTime() {
        BigDecimal decimal = new BigDecimal("0.1");
        check(new BigDecimal(0.1).compareTo(decimal) != 0, "double构造保留二进制近似");
        check(BigDecimal.valueOf(0.1).equals(decimal), "valueOf按double文本构造");
        BigDecimal a = new BigDecimal("1.0"), b = new BigDecimal("1.00");
        check(a.compareTo(b) == 0 && !a.equals(b), "数值比较与表示相等不同");
        check(new HashSet<>(List.of(a, b)).size() == 2 && new TreeSet<>(List.of(a, b)).size() == 1,
                "集合去重规则不同");
        expect(ArithmeticException.class, () -> BigDecimal.ONE.divide(new BigDecimal("3")));
        check(BigDecimal.ONE.divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP).equals(new BigDecimal("0.33")),
                "显式除法舍入");
        BigDecimal part = new BigDecimal("0.005");
        check(part.setScale(2, RoundingMode.HALF_UP).multiply(new BigDecimal("2")).equals(new BigDecimal("0.02")),
                "逐笔舍入");
        check(part.multiply(new BigDecimal("2")).setScale(2, RoundingMode.HALF_UP).equals(new BigDecimal("0.01")),
                "汇总舍入");
        expect(ArithmeticException.class, () -> new BigDecimal("1.1").longValueExact());
        expect(ArithmeticException.class, () -> new BigDecimal("9223372036854775808").longValueExact());
        Instant deadline = Instant.parse("2026-10-29T00:00:00Z");
        check(!expired(deadline, Clock.fixed(deadline.minusNanos(1), ZoneOffset.UTC)), "截止前未过期");
        check(expired(deadline, Clock.fixed(deadline, ZoneOffset.UTC)), "截止瞬间过期");
        check(expired(deadline, Clock.fixed(deadline.plusNanos(1), ZoneOffset.UTC)), "截止后过期");
        ZoneId paris = ZoneId.of("Europe/Paris");
        ZonedDateTime start = ZonedDateTime.of(2024, 3, 30, 12, 0, 0, 0, paris);
        check(Duration.between(start, start.plusDays(1)).toHours() == 23, "跨春季切换一天为23小时");
        check(start.plusHours(24).getHour() == 13, "经过24小时与下一天当地时刻不同");
        check(paris.getRules().getValidOffsets(LocalDateTime.of(2024, 3, 31, 2, 30)).isEmpty(), "春季缺失时刻");
        check(paris.getRules().getValidOffsets(LocalDateTime.of(2024, 10, 27, 2, 30)).size() == 2, "秋季重复时刻");
    }

    public static void main(String[] args) throws Exception {
        basics();
        generics();
        equality();
        resources();
        reflection();
        moneyAndTime();
        System.out.println("Java基础边界实验通过：" + checks + " 条断言");
    }
}
