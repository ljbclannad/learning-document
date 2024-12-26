# 1. GO和JAVA的区别
1. 语言设计理念
    1. JAVA是一种面向对象的编程语言，强调继承、多态、封装等OOP特性，运行在JVM上。JAVA的设计目标是建立一个具有高度灵活性和可扩展性的通用编程平台。
    2. GO是一种注重简洁和高效性的编程语言，主要面对系统级编程和并发处理。强调简单的语法和快速编译，并通过Goroutine和Channel提供并发支持。
2. 并发模型：
    1. JAVA基于操作系统线程，使用Thread和Executor框架来管理并发任务。通常需要显式地管理线程的创建、同步和资源共享
    2. GO：GO基于Coroutine（协程），通过Goroutine和Channel，实现了轻量级的并发处理。
3. 内存管理：
    1. JAVA使用GC机制管理内存
    2. GO也是用GC，但是设计上更加简洁，更适合处理大量并发请求，具有较低的暂停时间。

# 2. Go语言的优点
1. 自带GC
2. 静态编译，编译好后，扔服务器直接运行。
3. 简单的思想，没有继承，多态，类等。
4. 丰富的库和详细的开发文档。
5. 语法层支持并发，和拥有同步并发的channel类型，使并发开发变得非常方便。
6. 简洁的语法，提高开发效率，同时提高代码的阅读性和可维护性。
7. 超级简单的交叉编译，仅需更改环境变量。

# 3. Init函数和main函数的异同
1. 相同点：    
	1. 两个函数在定义时不能有任何的参数和返回值，且Go程序自动调用。
2. 不同点：    
	1. init可以应用于任意包中，且可以重复定义多个。
	2. main函数只能用于main包中，且只能定义一个。
3. init的执行顺序：    
	1. 对同一个go文件的`init()`调用顺序是从上到下的
	2. 对同一个package中不同文件是按文件名字符串比较“从小到大”顺序调用各文件中的`init()`函数。
	3. 对于不同的`package`，如果不相互依赖的话，按照main包中"先`import`的后调用"的顺序调用其包中的`init()`，如果`package`存在依赖，则先调用最早被依赖的`package`中的`init()`，最后调用`main`函数。

# 4. 下划线的作用
1. 当导入一个包时，该包下的文件里所有init()函数都会被执行，然而，有些时候我们并不需要把整个包都导入进来，仅仅是是希望它执行init()函数而已。这个时候就可以使用 import 引用该包。即使用【import _ 包路径】只是引用该包，仅仅是为了调用init()函数，所以无法通过包名来调用包中的其他函数。

# 5. Go语言中的指针
1. Go语言中的指针操作非常简单，只需要记住两个符号：`&`（取地址）和`*`（根据地址取值）
2. 在对普通变量使用&操作符取地址后会获得这个变量的指针，然后可以对指针使用`*`操作，也就是指针取值
```
func main() {
    //指针取值
    a := 10
    b := &a // 取变量a的地址，将指针保存到b中
    fmt.Printf("type of b:%T\n", b)
    c := *b // 指针取值（根据指针去内存取值）
    fmt.Printf("type of c:%T\n", c)
    fmt.Printf("value of c:%v\n", c)
}

    type of b:*int
    type of c:int
    value of c:10

func modify1(x int) {
    x = 100
}

func modify2(x *int) {
    *x = 100
}

func main() {
    a := 10
    modify1(a)
    fmt.Println(a) // 10
    modify2(&a) //传递地址才有效，要不然就是值传递
    fmt.Println(a) // 100
}
```

# 6. select语句
1. select是Go中的一个控制结构，类似于switch语句，用于处理异步IO操作。select会监听case语句中channel的读写操作，当case中channel读写操作为非阻塞状态（即能读写）时，将会触发相应的动作。 select中的case语句必须是一个channel操作
2. select中的default子句总是可运行的。
3. 如果有多个case都可以运行，select会随机公平地选出一个执行，其他不会执行。
4. 如果没有可运行的case语句，且有default语句，那么就会执行default的动作。
5. 如果没有可运行的case语句，且没有default语句，select将阻塞，直到某个case通信可以运行
```
//比如在下面的场景中，使用全局resChan来接受response，如果时间超过3S,resChan中还没有数据返回，则第二条case将执行
var resChan = make(chan int)
// do request
func test() {
    select {
    case data := <-resChan:
        doData(data)
    case <-time.After(time.Second * 3):
        fmt.Println("request time out")
    }
}

func doData(data int) {
    //...
}
```
# 7. 函数类型的应用
```
package main

import "fmt"

func test(fn func() int) int {
    return fn()
}
// 定义函数类型。
type FormatFunc func(s string, x, y int) string 

func format(fn FormatFunc, s string, x, y int) string {
    return fn(s, x, y)
}

func main() {
    s1 := test(func() int { return 100 }) // 直接将匿名函数当参数。

    s2 := format(func(s string, x, y int) string {
        return fmt.Sprintf(s, x, y)
    }, "%d, %d", 10, 20)

    println(s1, s2)
}
```
# 8. 延迟调用(defer)
1. defer的特性
	1. 关键字 defer 用于注册延迟调用。
	2. 这些调用直到 return 前才被执。因此，可以用来做资源清理，return并非原子操作，共分为(1) 返回值赋值；(2) RET指令两步操作。而defer语句执行在赋值之后，RET之前。defer、return、返回值三者的执行是：return最先执行，先将结果写入返回值中（即赋值）；接着defer开始执行一些收尾工作；最后函数携带当前返回值退出（即返回值）。
	3. 多个defer语句，按先进后出的方式执行。
	4. defer语句中的变量，在defer声明时就决定了。
2. defer的变量快照失效的情况：
	1. 匿名函数闭包：当defer语句中使用的匿名函数捕获了外部变量时，如果变量的值在defer语句定义后发生改变，defer执行时会使用变化后的值
	2. 引用类型：当defer引用持有引用类型的变量，指向的内容发生变化

# 9. 异常处理（导致关键流程出现不可修复性错误的使用 panic，其他使用 error）
1. panic
	1.  内置函数
	2. 假如函数F中书写了panic语句，会终止其后要执行的代码，在panic所在函数F内如果存在要执行的defer函数列表，按照defer的逆序执行
	3. 返回函数F的调用者G，在G中，调用函数F语句之后的代码不会执行，假如函数G中存在要执行的defer函数列表，按照defer的逆序执行
	4. 直到goroutine整个退出，并报告错误
2. recover
	1. 内置函数
	2. 用来控制一个goroutine的panicking行为，捕获panic，从而影响应用的行为
	3. 一般的调用建议
		1. 在defer函数中，通过recever来终止一个goroutine的panicking过程，从而恢复正常代码的执行
		2. 可以获取通过panic传递的error
3. 注意点
	1. 利用recover处理panic指令，defer 必须放在 panic 之前定义，另外 recover 只有在 defer 调用的函数中才有效。否则当panic时，recover无法捕获到panic，无法防止panic扩散。
	2. recover 处理异常后，逻辑并不会恢复到 panic 那个点去，函数跑到 defer 之后的那个点。
	3. 多个 defer 会形成 defer 栈，后定义的 defer 语句会被最先调用。
4. 自定义error:
	1. 在recover捕捉到panic异常时定义err后抛出
	2. 定义err,直接判断并抛出，if err != nil

# 10. 方法定义（TODO）
1. func (recevier type) methodName(参数列表)(返回值列表){}
2. 普通函数与方法的区别
	1. 对于普通函数，接收者为值类型时，不能将指针类型的数据直接传递，反之亦然。
	2. 对于方法（如struct的方法），接收者为值类型时，可以直接用指针类型的变量调用方法，反过来同样也可以。

# 11.格式标识符
1. %p:打印指针的值，即地址
2. %d：打印十进制整数
3. %s：打印字符串
4. %f：打印浮点数
5. %.2f：打印保存小数点后2位的浮点数
6. %t：打印布尔值
7. %x：十六进制打印整数
8. %b：二进制打印整数
9. %v：打印值的默认格式


# 12.并发
## 1. Goroutine
1. 通过通信来共享内存，而不是共享内存来通信
2. goroutine的概念类似于线程，但 goroutine是由Go的运行时（runtime）调度和管理的。Go程序会智能地将 goroutine 中的任务合理地分配给每个CPU。Go语言之所以被称为现代化的编程语言，就是因为它在语言层面已经内置了调度和上下文切换的机制
3. 启动goroutine的方式非常简单，只需要在调用的函数（普通函数和匿名函数）前面加上一个go关键字
4. 启动多个goroutine(类似于java的countDownLatch)
5. 如果主协程退出了，其他任务会同步取消
6. GPM:
	1. G很好理解，就是个goroutine的，里面除了存放本goroutine信息外 还有与所在P的绑定等信息。
	2. P管理着一组goroutine队列，P里面会存储当前goroutine运行的上下文环境（函数指针，堆栈地址及地址边界），P会对自己管理的goroutine队列做一些调度（比如把占用CPU时间较长的goroutine暂停、运行后续的goroutine等等）当自己的队列消费完了就去全局队列里取，如果全局队列里也消费完了会去其他P的队列里抢任务。
	3. M（machine）是Go运行时（runtime）对操作系统内核线程的虚拟， M与内核线程一般是一一映射的关系， 一个groutine最终是要放到M上执行的
	4. P与M一般也是一一对应的。他们关系是： P管理着一组G挂载在M上运行。当一个G长久阻塞在一个M上时，runtime会新建一个M，阻塞G所在的P会把其他的G 挂载在新建的M上。当旧的G阻塞完成或者认为其已经死掉时 回收旧的M。
	5. P的个数是通过runtime.GOMAXPROCS设定（最大256），Go1.5版本之后默认为物理线程数。 在并发量大的时候会增加一些P和M，但不会太多，切换太频繁的话得不偿失。
	6. 单从线程调度讲，Go语言相比起其他语言的优势在于OS线程是由OS内核来调度的，goroutine则是由Go运行时（runtime）自己的调度器调度的，这个调度器使用一个称为m:n调度的技术（复用/调度m个goroutine到n个OS线程）。 其一大特点是goroutine的调度是在用户态下完成的， 不涉及内核态与用户态之间的频繁切换，包括内存的分配与释放，都是在用户态维护着一块大的内存池， 不直接调用系统的malloc函数（除非内存池需要改变），成本比调度OS线程低很多。 另一方面充分利用了多核的硬件资源，近似的把若干goroutine均分在物理线程上， 再加上本身goroutine的超轻量，以上种种保证了go调度方面的性能。
```
//启动多个
var wg sync.WaitGroup

func hello(i int) {
    defer wg.Done() // goroutine结束就登记-1
    fmt.Println("Hello Goroutine!", i)
}
func main() {

    for i := 0; i < 10; i++ {
        wg.Add(1) // 启动一个goroutine就登记+1
        go hello(i)
    }
    wg.Wait() // 等待所有登记的goroutine都结束
}
```

## 2. Runtime
1. 通过runtime.Goexit()可以直接退出当前线程
2. 通过runtime.Gosched()可以让出CPU时间片（并发核心就是通过时间片轮换任务）

## 3. Channel
1. Go语言的并发模型是CSP（Communicating Sequential Processes），提倡通过通信共享内存而不是通过共享内存而实现通信。
2. 如果说goroutine是Go程序并发的执行体，channel就是它们之间的连接。channel是可以让一个goroutine发送特定值到另一个goroutine的通信机制。
3. Go 语言中的通道（channel）是一种特殊的类型。通道像一个传送带或者队列，总是遵循先入先出（First In First Out）的规则，保证收发数据的顺序。每一个通道都是一个具体类型的导管，也就是声明channel的时候需要为其指定元素类型。
4. channel操作
	1. 定义通道 ch:= make(chan int)
	2. 将一个值发送到通道：ch <- 10
	3. 从一个通道中接收值  x:= <-10 
	4. 关闭通道：close(ch)
		1. 对一个关闭的通道再发送值就会导致panic。
		2. 对一个关闭的通道进行接收会一直获取值直到通道为空。
		3. 对一个关闭的并且没有值的通道执行接收操作会得到对应类型的零值。
		4. 关闭一个已经关闭的通道会导致panic。
5. 无缓冲通道
	1. 无缓冲通道上的发送操作会阻塞，直到另一个goroutine在该通道上执行接收操作，这时值才能发送成功，两个goroutine将继续执行。相反，如果接收操作先执行，接收方的goroutine将阻塞，直到另一个goroutine在该通道上发送一个值。
	2. 使用无缓冲通道进行通信将导致发送和接收的goroutine同步化。因此，无缓冲通道也被称为同步通道。
6. 通道的循环取值
```
func main() {
    ch1 := make(chan int)
    ch2 := make(chan int)
    // 开启goroutine将0~100的数发送到ch1中
    go func() {
        for i := 0; i < 100; i++ {
            ch1 <- i
        }
        close(ch1)
    }()
    // 开启goroutine从ch1中接收值，并将该值的平方发送到ch2中
    go func() {
        for {
            i, ok := <-ch1 // 通道关闭后再取值ok=false
            if !ok {
                break
            }
            ch2 <- i * i
        }
        close(ch2)
    }()
    // 在主goroutine中从ch2中接收值打印
    for i := range ch2 { // 通道关闭后会退出for range循环
        fmt.Println(i)
    }
}
```

## 4. 并发锁
1. 互斥锁
```
var x int64
var wg sync.WaitGroup
var lock sync.Mutex

func add() {
    for i := 0; i < 5000; i++ {
        lock.Lock() // 加锁
        x = x + 1
        lock.Unlock() // 解锁
    }
    wg.Done()
}
func main() {
    wg.Add(2)
    go add()
    go add()
    wg.Wait()
    fmt.Println(x)
} 
```
2. 读写互斥锁
	1. 互斥锁是完全互斥的，但是有很多实际的场景下是读多写少的，当我们并发的去读取一个资源不涉及资源修改的时候是没有必要加锁的，这种场景下使用读写锁是更好的一种选择。读写锁在Go语言中使用sync包中的RWMutex类型。
```
var (
    x      int64
    wg     sync.WaitGroup
    lock   sync.Mutex
    rwlock sync.RWMutex
)

func write() {
    // lock.Lock()   // 加互斥锁
    rwlock.Lock() // 加写锁
    x = x + 1
    time.Sleep(10 * time.Millisecond) // 假设读操作耗时10毫秒
    rwlock.Unlock()                   // 解写锁
    // lock.Unlock()                     // 解互斥锁
    wg.Done()
}

func read() {
    // lock.Lock()                  // 加互斥锁
    rwlock.RLock()               // 加读锁
    time.Sleep(time.Millisecond) // 假设读操作耗时1毫秒
    rwlock.RUnlock()             // 解读锁
    // lock.Unlock()                // 解互斥锁
    wg.Done()
}

func main() {
    start := time.Now()
    for i := 0; i < 10; i++ {
        wg.Add(1)
        go write()
    }

    for i := 0; i < 1000; i++ {
        wg.Add(1)
        go read()
    }

    wg.Wait()
    end := time.Now()
    fmt.Println(end.Sub(start))
}
```
# 13. 定时器（TODO）


# 14. 访问私有成员：
1. 首字母的大小决定了数据成员的私有性，小写为私有
2. 私有成员包内直接访问
3. 包外使用公开接口访问
4. 使用反射访问


# 15. 接口
1. 一个类型只需要定义接口要求的方法，就可以被视为实现了该接口
2. 本质上是一个动态类型和动态值的组合
	1. 动态类型：接口持有的具体数据的类型
	2. 动态值：接口持有的具体数据的值或引用
3. ```type 接口类型名 interface{
        方法名1( 参数列表1 ) 返回值列表1
        方法名2( 参数列表2 ) 返回值列表2
        …
    }```
3. 值接收者和指针接收者实现接口的差距
	1. 使用值接收者实现接口之后，不管是dog结构体还是结构体指针`*dog`类型的变量都可以赋值给该接口变量。因为Go语言中有对指针类型变量求值的语法糖，dog指针fugui内部会自动求值`*fugui`
	2. 使用指针接收者后只能使用结构体指针`*dog`类型的值


# 16. 闭包（TODO）


# 17. 通过指针变量p访问其成员变量的方式
	  b := Book{title : "Go Programming"}
	  p := &b
1. 使用显式解引用
	1. `(*p).title
2. 简化解引用
	1. `p.title`

# 18. 所有的T类型都有\*T类型吗
1. 除了接口类型，其他数据类型都有\*T类型

# 19.数组和切片的区别
1. 长度不同：数组还有固定长度的序列，而切片是基于数组构建的一种灵活、可变长度的序列
2. 内存管理不同：数组的底层存储是在栈上，而切片的底层是在堆上，因此切片需要进行内存分配和垃圾回收，而数组不需要
3. 类型不同：数组的优势在于它是值类型，可以通过赋值操作来赋值一个数组，而切片是引用类型，复制一个切片只是复制了指向底层数组的指针，而不是复制了整个底层数组
4. 使用场景不同：数组适用于需要固定大学且安全复制的场景，而切片适用于需要动态增减的操作，提供灵活且高效的管理数组的功能
5. 拷贝速率不同：由于切片的拷贝只复制一个指针，而不是复制整个底层结构，所以切片的拷贝速度远优于数组
6. 创建数组：`var arr [5] int`，创建切片:`s := []int{1,2,3}
7. 