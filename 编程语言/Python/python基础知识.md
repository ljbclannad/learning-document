1. 字典的值是不可变的

2. string.strip(str)，表示去掉首尾的 str 字符串；string.lstrip(str)，表示只去掉开头的 str 字符串；string.rstrip(str)，表示只去掉尾部的 str 字符串。

3. 把 str 强制转换为 int 请用 int()，转为浮点数请用 float()

4. 在条件语句的末尾必须加上冒号（:），这是 Python 特定的语法规范。

5. ```python
   MIN_VALUE = 1
   MAX_VALUE = 10
   def validation_check(value):
       global MIN_VALUE //函数内部的变量 MIN_VALUE，就是之前定义的全局变量，并不是新的全局变量，也不是局部变量。这样，程序就可以在函数内部访问全局变量，并修改它的值了。
       ...
       MIN_VALUE += 1
       ...
   validation_check(5)
   ```

6. 类似的，对于嵌套函数来说，内部函数可以访问外部函数定义的变量，但是无法修改，若要修改，必须加上 nonlocal 这个关键字

   ```python
   def outer():
       x = "local"
       def inner():
           nonlocal x # nonlocal关键字表示这里的x就是外部函数outer定义的变量x
           x = 'nonlocal'
           print("inner:", x)
       inner()
       print("outer:", x)
   outer()
   
   输出
   
   inner: nonlocal
   outer: nonlocal
   ```

7. 函数 map(function, iterable) 的第一个参数是函数对象，第二个参数是一个可以遍历的集合，它表示对 iterable 的每一个元素，都运用 function 这个函数。

8. filter() 函数表示对 iterable 中的每个元素，都使用 function 判断，并返回 True 或者 False，最后将返回 True 的元素组成一个新的可遍历的集合。

9. reduce(function, iterable) 函数，它通常用来对一个集合做一些累积操作。

10. from utils.class_utils import *

11. import 在导入文件的时候，会自动把所有暴露在外面的代码全都执行一遍。因此，如果你要把一个东西封装成模块，又想让它可以执行的话，你必须将要执行的代码放在 if __name__ == '__main__'下面。

12. 出于对性能优化的考虑，Python 内部会对 -5 到 256 的整型维持一个数组，起到一个缓存的作用。这样，每次你试图创建一个 -5 到 256 范围内的整型数字时，Python 都会从这个数组中返回相对应的引用，而不是重新开辟一块新的内存空间。

13. 浅拷贝，是指重新分配一块内存，创建一个新的对象，里面的元素是原对象中子对象的引用。因此，如果原对象中的元素不可变，那倒无所谓；但如果元素可变，浅拷贝通常会带来一些副作用，尤其需要注意。

14. ```python
    l1 = [[1, 2], (30, 40)]
    l2 = list(l1)
    l1.append(100)
    l1[0].append(3)
    
    l1
    [[1, 2, 3], (30, 40), 100]
    
    l2
    [[1, 2, 3], (30, 40)]
    
    l1[1] += (50, 60)
    l1
    [[1, 2, 3], (30, 40, 50, 60), 100]
    
    l2
    [[1, 2, 3], (30, 40)]
    ```

15. 深度拷贝则会递归地拷贝原对象中的每一个子对象，因此拷贝后的对象和原对象互不相关。另外，深度拷贝中会维护一个字典，记录已经拷贝的对象及其 ID，来提高效率并防止无限递归的发生。

16. 在Python中：

    - 变量的赋值，只是表示让变量指向了某个对象，并不表示拷贝对象给变量；而一个对象，可以被多个变量所指向。
    - 可变对象（列表，字典，集合等等）的改变，会影响所有指向该对象的变量。
    - 对于不可变对象（字符串、整型、元组等等），所有指向该对象的变量的值总是一样的，也不会改变。但是通过某些操作（+= 等等）更新不可变对象的值时，会返回一个新的对象。
    - 变量可以被删除，但是对象无法被删除。

17. 最简单的装饰器：

    ```python
    def my_decorator(func):
        def wrapper():
            print('wrapper of decorator')
            func()
        return wrapper
    
    @my_decorator
    def greet():
        print('hello world')
    
    greet()
    ```

18. 带有多个参数的装饰器：

    ```python
    def argsDecorator(func):
        def wrapper(*args,**kwargs):
            print("args Wrappers")
            func(*args,**kwargs)
        return wrapper;   
    
    
    @argsDecorator
    def argsGreet(name,age):
        print(name + "---"+age)
    
    argsGreet("Liu","33")
    ```

19. 自定义参数的装饰器：

    ```python
    def repeat(num): 
        def my_decorator(func): 
            def wrapper(*args, **kwargs): 
                for i in range(num): 
                    print('wrapper of decorator') 
                    func(*args, **kwargs) 
            return wrapper 
        return my_decorator
            
    @repeat(4)
    def greet(message): 
        print(message)
    
    
    greet("hello")
    ```

20. 生成器的概念应运而生，在你调用 next() 函数的时候，才会生成下一个变量。生成器在 Python 的写法是用小括号括起来，(i for i in range(100000000))，即初始化了一个生成器。

21. 所谓 Sync，是指操作一个接一个地执行，下一个操作必须等上一个操作完成后才能执行。而 Async 是指不同操作间可以相互交替执行，如果其中的某个操作被 block 了，程序并不会等待，而是会找出可执行的操作继续执行。

22. 因为协程是单线程，所以无法利用多核 CPU。

23. 通过enumerate函数处理列表之后再遍历可以同时获得元素索引和值

    
