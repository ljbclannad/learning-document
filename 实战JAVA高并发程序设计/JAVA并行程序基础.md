# 1. 线程的基本操作

## 1.1 新建线程

1. 新建线程只需要new关键字创建一个线程对象，并且将它start()起来即可。start方法会新建一个线程并让这个线程执行run()方法。

2. 不要用run方法来开启新线程，它只会在当前线程中串行执行run方法中的代码。

3. 在默认情况下，线程Tread的run()方法什么都没有做，如果想让线程做点什么，就必须重写run()方法，把你的任务加进去

   <img src="/Users/lejinbo/Library/Application Support/typora-user-images/image-20220420145333145.png" alt="image-20220420145333145" style="zoom:50%;" />

4. 实现Runnable接口也可以实现同样的操作。Thread.run()方法源码调用了Runnable的run()方法。

   ```java
   @Override
   public void run() {
       if (target != null) {
           target.run();
       }
   }
   ```

## 1.2 线程中断

1. 严格地讲，线程中断并不会使线程立即退出，而是给线程发送一个通知，告诉目标线程需要退出。至于目标线程接到通知后如何处理则完全由目标线程决定，如果中断后线程立即无条件退出，我们又会遇到stop()方法的老问题。
2. ![image-20220420151455629](/Users/lejinbo/Library/Application Support/typora-user-images/image-20220420151455629.png)
3. Thread.interrupt()方法通知目标线程中断，也就是设置中断标志位。
4. Thread.isInterrupted()方法判断当前线程是否被中断（通过判断中断标志位）。
5. 静态方法Thread.interrupted()方法也可用来判断当前线程的终端状态，但同时会清楚当前线程的中断标志位。

## 1.3 等待(wait)和通知(notify)

1. 在线程A中，调用了obj.wait()方法，那么线程A就会停止执行，转为等待状态。一直等到其他线程调用obj.notify()方法。
2. 如果一个线程调用了obj.wait()方法，那么它就会进入obj对象的等待队列。这个等待队列中可能会有多个线程，当obj.notify()方法被调用时，它就会从这个等待队列中随机选择一个线程将其唤醒，这个选择是不公平的。

<img src="/Users/lejinbo/Library/Application Support/typora-user-images/image-20220420172221213.png" alt="image-20220420172221213" style="zoom:50%;" />

3. 除了notify()方法外，obj对象还有一个类似的notifyAll()方法，它会唤醒在这个等待队列中所有等待的线程。
4. wait方法和notify方法都必须要放在对应的synchronized语句中。

## 1.4 等待线程结束和谦让

1. Join()方法的本质是让调用线程wait()在当前的线程对象实例上。当线程执行完成后，被等待的线程会在退出前调用notifyAll()方法通知所有的等待线程继续执行。
2. Yield()会使当前线程让出CPU，但是还会进行CPU资源的竞争。



# 2. volatile与JMM

1. 当你用关键字volatile声明一个变量时，就等于告诉虚拟机这个变量极有可能会被某些程序或者线程修改。



# 3. synchronized作用域

1. 作用于对象：对给定对象加锁，进入同步代码前要获得给定对象的锁。
2. 作用于实例方法：相当于对当前实例类加锁，进步同步代码前要获得当前实例的锁。
3. 作用于静态方法：相当于对当前类加锁，进入同步代码前要获得当前类的锁。



# 4. 错误的加锁

1. 锁加的对象属于不可变对象，如加在Integer或者String对象上，每次针对该对象操作都会生成新的对象并指向当前对象，所以加的锁不会生效。