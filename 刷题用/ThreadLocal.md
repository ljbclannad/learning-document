ThreadLocal详解：

​	ThreadLocal的作用主要是做数据隔离，填充的数据只属于当前线程，数据的变化对于其他线程来说是隔离的，同时可以防止被其他线程篡改



ThreadLocal的set源码：

```java
public void set(T value) {
    Thread t = Thread.currentThread(); //获取当前线程
    ThreadLocalMap map = getMap(t);//获取ThreadLocalMap对象
    if (map != null)
        map.set(this, value); //set
    else
        createMap(t, value); //为空创建一个map对象
}
```

```java
ThreadLocalMap getMap(Thread t) {
    return t.threadLocals;
}

 ThreadLocal.ThreadLocalMap threadLocals = null;
```

ThreadLocalMap是当前线程Thread一个叫threadLocals的变量中获取的,所以实现了数据隔离。



ThreadLocalMap底层架构：

​	threadLocalMap跟hashMap不一样，没有实现Map接口，并且Entry继承了WeakReference(弱引用)，也没有HashMap中的next，所以是数组形式的，如果为强引用，当前线程结束后也不会被回收，会导致内存泄漏

```java
static class ThreadLocalMap {

    static class Entry extends WeakReference> {
        /** The value associated with this ThreadLocal. */
        Object value;

        Entry(ThreadLocal k, Object v) {
            super(k);
            value = v;
        }
    }为什么需要数组：一个thread可能创建多个threadLocal,这几个threadLocal都需要往threadLocalMap中存放数据，所以是个数组。没有链表怎么解决hash冲突：线性探测法set方法步骤：1. ThreadLocalMap在存储的时候会给每一个ThreadLocal对象一个threadLocalHashCode，在插入过程中，根据ThreadLocal对象的hash值，定位到table中的位置i，**int i = key.threadLocalHashCode & (len-1)**。
1. 如果当前位置是空的，就初始化一个Entry对象放在位置i上；
1. 如果位置i不为空，如果这个Entry对象的key正好是即将设置的key，那么就刷新Entry中的value；
1. 如果位置i的不为空，而且key不等于entry，那就找下一个空位置，直到为空为止。get方法1. 与set相同，如果没有找到就到下一个ThreadLocal的实例实际上存放在堆上还是栈上：​	因为ThreadLocal实例实际上也是被其创建的类持有（更顶端应该是被线程持有），而ThreadLocal的值其实也是被线程实例持有，它们都是位于堆上，只是通过一些技巧将可见性修改成了线程可见。​	共享线程的threadLocal数据（父子线程）：​	使用InheritableThreadLocal可以实现多个线程访问ThreadLocal的值，我们在主线程中创建一个InheritableThreadLocal的实例，然后在子线程中得到这个InheritableThreadLocal实例设置的值。private void test() {    
  final ThreadLocal threadLocal = new InheritableThreadLocal();       threadLocal.set("帅得一匹");   
  Thread t = new Thread() {            
    @Override            
    public void run() {                  
      super.run();                  
      Log.i( "张三帅么 =" + threadLocal.get());            
    }      
  };            
  t.start(); 
} Thead.init创建时会创建InheritableThreadLocals​	public class Thread implements Runnable { ……  if (inheritThreadLocals && parent.inheritableThreadLocals != null)   this.inheritableThreadLocals=ThreadLocal.createInheritedMap(parent.inheritableThreadLocals); ……}TransmittableThreadLocal（用来解决线程池内线程变量通信的问题）：​	线程池的核心线程池在为开启释放核心线程池的情况下，将会被重复使用，但是InheritableThreadLocal中变量的维护在新建线城时才会进行一次赋值，所以出现了修改之后，新提交的任务，无法获取更新的InheritableThreadLocal变量值。public class Demo {

    public static final InheritableThreadLocal t = new InheritableThreadLocal();

    public static void main(String[] args) {
        t.set("test");
        ExecutorService executorService = Executors.newFixedThreadPool(1);
        Runnable runnable1 = () -> {
            System.out.println("new修改前:" + t.get());
        };
        Runnable runnable2 = ()->{
            try {
                Thread.sleep(1000);
            } catch (InterruptedException e) {
                e.printStackTrace();
            }
            System.out.println("new修改后:"+t.get());
        };
        executorService.submit(runnable1);
        System.out.println("main修改前:"+t.get());
        t.set("test1");
        System.out.println("main修改后:"+t.get());
        executorService.submit(runnable2);
        System.out.println("main最后:"+t.get());
    }

}

输出：
main修改前:test
new修改前:test
main修改后:test1
main最后:test1
new修改后:test​	TransmittableThreadLocal的实现原理：​		TransmittableThreadLocal继承InheritableThreadLocals​		实现多线程之间的值传递：父线程把任务提交给线程池时一同附上此刻自己的ThreadLocalMap，包装在task里，待线程池中某个线程执行到该任务时，用task里的ThreadLocalMap赋盖当前线程ThreadLocalMap，这样就完成了父线程向池化的子线程传递线程私有数据的目标。为了避免数据污染，待任务执行完后，线程归还回线程池之前，还需要还原ThreadLocalMap​		用代码简单描述这个逻辑：​	​	我们把"拷贝"父线程TheadLocalMap的行为称为capture(拍照)，一个很生动形象的词：将父线程提交任务时刻的ThreadLocal值拍个快照并保存起来，后续使用​	用MyTask的threadLocalValues(快照)去覆盖当前线程的ThreadLocalMap。我们称这个动作为replay(重放)public void run() {
    Map, Object> copied = (Map)this.copiedRef.get();
    if (copied != null && (!this.releaseTtlValueReferenceAfterRun || this.copiedRef.compareAndSet(copied, (Object)null))) {
        Map backup = TransmittableThreadLocal.backupAndSetToCopied(copied);

        try {
            this.runnable.run();
        } finally {
            TransmittableThreadLocal.restoreBackup(backup);
        }

    } else {
        throw new IllegalStateException("TTL value reference is released after run!");
    }
}  private static InheritableThreadLocal, ?>> holder = new InheritableThreadLocal, ?>>() {
        protected Map, ?> initialValue() {
            return new WeakHashMap();
        }

        protected Map, ?> childValue(Map, ?> parentValue) {
            return new WeakHashMap(parentValue);
        }
    };

public final T get() {
    T value = super.get();
    if (null != value) {
        this.addValue();
    }

    return value;
}

public final void set(T value) {
    super.set(value);
    if (null == value) {
        this.removeValue();
    } else {
        this.addValue();
    }
}

 private void addValue() {
        if (!((Map)holder.get()).containsKey(this)) {
            ((Map)holder.get()).put(this, (Object)null);
        }

    }

    private void removeValue() {
        ((Map)holder.get()).remove(this);
    }​	threadLocal的内存泄漏：​	根本原因是因为生命周期跟thread绑定，thread结束threadLocal就会销毁​	THreadLocalMap中的Entry的key使用的是ThreadLocal对象的弱引用，在没有其他地方对ThreadLoca依赖，ThreadLocalMap中的ThreadLocal对象就会被回收掉，但是对应的不会被回收，这个时候Map中就可能存在key为null但是value不为null的项，这需要实际的时候使用完毕及时调用remove方法避免内存泄漏。1. 使用ThreadLocal.remove()方法移除变量
1. 使用设置ThreadLocal = null 来移除变量，ThrealLocalMap的实现使用了弱引用。链路追踪：​	Java语言第三方的日志工具都提了日志链路追踪的方案，比如logback的MDC，MDC的使用也很简单，就是在业务的开始put一个key-value，这个key-value就能贯穿整个线程的执行流程，使用代码如下：​	MDC.put("traceId", UUID.randomUUID().toString()); ​	MDC虽然提供了一个现成的整个执行流程的日志追踪的方案，但是也只是一个线程，假如一个线程中又启动了另一个线程呢，这时MDC就无法完成完整的链路追踪工作了，因为MDC是基于ThreadLocal实现的，所以当一个线程中启动另一个线程的时候两个线程的TraceId就隔离开了，也就无法做到日志链路追踪。​	重新MDCAdapter，用TransmittableThreadLocal替换ThreadLocal，解决多线程，异步情况x-glabal-sessionId无法传递问题
```