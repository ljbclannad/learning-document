Spring IOC（控制反转）:

​	理念：将原本在程序中手动创建对象的控制权交由框架处理，这里的框架指的是Spring

​	控制：指的是对象创建（实例化，管理）的权利

​	反转：控制权交给外部环境

​	将对象之间的相互依赖关系交给 IoC 容器来管理，并由 IoC 容器完成对象的注入。这样可以很大程度上简化应用的开发，把应用从复杂的依赖关系中解放出来。

​	Spring 启动时读取应用程序提供的 Bean 配置信息，并在 Spring 容器中生成一份相应的 Bean 配置注册表，然后根据这张注册表实例化 Bean，装配好 Bean 之间的依赖关系，为上层应用提供准备就绪的运行环境。 其中 Bean 缓存池为 HashMap 实现



IOC容器的创建时间：

​	在new ApplicationContext()时会发生IOC容器加载



IOC的加载过程：

	1. 读取配置文件，创建一个BeanDefintion()对象，放入BeanDefintionMap(beanName,BeanDefintion)中
	1. 循环所有的BeanDefintion()，交给BeanFactory（简单工厂设计模式）生产Bean（getBean）。创建流程如下：
	1. 去一级缓存（Map<BeanName,Bean示例对象>容器）中判断是否创建完成，如果已经创建则直接返回，否则进行创建
	1. 拿到当前的BeanDefintion对象，获取BeanDefintion的beanClass对象，通过反射实例化Bean
	1. 进行属性注入（解析@AutoWired等注入注解，参考Spring生命周期），初始化完之后放入一级缓存，如果这时候有其他的BeanB没有创建，则会调用第3步去创建BeanB，如果依赖A则产生循环依赖



一级缓存（SingletonObjects）能够解决死循环的问题：

	1. 在上面第4步结束后就将实例化的Bean放入到一级缓存中，再进行第5步操作，这时候BeanB会在一级缓存中找到了BeanA的实例化，就解决了死循环。

	2. 操作1会存在有多线程的问题，如果这时候进来2个线程，线程1在第4步的时候在一级缓存中创建了实例，线程2进来的时候直接就能从一级缓存中获取到线程1创建的BeanA实例，但这时候BeanA实例还没有进行过属性注入等操作，所以线程2获取到的实例并不完整，可以在getBean方法上加锁解决
	2. 操作2可能会导致阻塞线程3进来获取BeanC的操作，这时候就需要获取二级缓存
	2. <img src="/Users/lejinbo/Library/Application Support/typora-user-images/image-20220112172509542.png" alt="image-20220112172509542" style="zoom:50%;" />



二级缓存（二级缓存和一级缓存的最主要区别用于解决并发情况下的Bean获取（在一级缓存加锁的条件下影响其他线程获取其他Bean））：

​	1. 在一级缓存的基础上进行操作：添加二级缓存以及去掉获取一级缓存时的锁，仅在操作二级缓存时加锁

​	2. 创建BeanA的流程修改为：在一级缓存中没有获取到，则实例化BeanA，并将实例化后的BeanA放到二级缓存中，再进行属性注入操作，将属性注入完的完整的BeanA放入一级缓存，删除二级缓存中创建的实例化的BeanA。

​	3. 解决死循环：BeanB创建时先会从一级缓存中获取BeanA的实例，由于这时候BeanA卡在BeanB的注入中（产生了循环依赖），所以一级缓存中并没有BeanA完整的实例，这时BeanB就会去二级缓存中查找BeanA的实例，发现BeanA的实例已经存在于二级缓存中，解决死循环，BeanB就创建完成

​	4. 解决获取的并不完整的情况（即一级缓存的操作2的情况）：线程1进来将实例化的BeanA放入到二级缓存中，由于对二级缓存操作进行了加锁操作，所以线程2在获取BeanA时被线程1阻塞，只能等到线程1获取到完整的BeanA后才能进入，但是由于线程锁加的位置是在获取一级缓存之后，线程2在线程1执行完之后走的是获取二级缓存的逻辑，二级缓存中没有BeanA的实例（在线程1实例化完之后已经被删除），又会执行创建BeanA的流程，解决方案：（使用双重检查锁，在线程2去创建BeanA的时候再去一级缓存中获取一遍BeanA的实例，这时候会发现线程1已经创建了，直接返回）

​	5. 解决阻塞其他线程的问题：线程3会从未加锁的一级缓存中获取BeanC，不会被线程1，2阻塞

​	<img src="/Users/lejinbo/Library/Application Support/typora-user-images/image-20220112172602453.png" alt="image-20220112172602453" style="zoom:50%;" />





为什么要三级缓存，二级缓存不能解决（二级缓存在解决循环依赖的动态代理时会生成多个动态代理）：

​	 Spring规定动态代理是在初始化之后创建的。但是循环依赖是在属性赋值步骤就发生，所以BeanB中的BeanA并没有创建动态代理，因此普通的Bean可以在初始化之后创建动态代理，但是循环依赖的Bean需要在循环依赖的流程图中创建动态代理

	1. 放入二级缓存前创建BeanA的动态代理，然后将BeanA的动态代理放入二级缓存，这个时候BeanB获取到的BeanA就为动态代理对象，但是在一级缓存中的BeanA还不是动态代理（只存放二级缓存中），解决方案：将二级缓存中的BeanA的动态代理放入至一级缓存中。
	1. 操作1导致所有的动态代理都在初始化之前就创建完成，违背了Bean的生命周期，因此在操作1的情况下需要增加条件判断：只有出现循环依赖才创建代理，判断逻辑：只有当一个Bean第二次创建（二级缓存中已经存在BeanA）的时候才能判断他是循环依赖（即BeanA.getBeanB,BeanB又去创建了BeanA），说明BeanA发生了循环依赖
	1. 但是如果BeanA有多个循环依赖的情况，那么会存在BeanA创建了多次动态代理，及BeanB处理循环依赖的时候创建了BeanA的动态代理，BeanC处理循环依赖的时候又创建了动态代理，这时候就需要三级缓存
	1. 三级缓存解决方案：将生成的动态代理放到三级缓存中，在下一次BeanC循环依赖的时候从三级缓存中获取



一级缓存解决了单例性。二级缓存可以解决单例性和性能问题。三级缓存可以解决循环依赖的动态代理

缓存并没有解决多例Bean的循环依赖：多例Bean没有存放在一级缓存中。



如果Spring中有多个构造方法，但是没有无参的方法，Spring初始化会报错，

如果存在多个构造方法并且有无参的构造方法，则优先调用无参的方法

如果存在一个构造方法，无论这个构造方法是否有参数都会调用这个构造方法

可以用Autowired注解指定构造方法



实例化和初始化的区别：

​	实例化获取当前类的示例对象

​	初始化会回调初始化方法



bean的生命周期：

```
	Bean容器找到配置文件中 Spring Bean 的定义。
​	Bean容器利用Java Reflection API创建一个Bean的实例。
​	如果涉及到一些属性值 利用set方法设置一些属性值。
​	如果Bean实现了BeanNameAware接口，调用setBeanName()方法，传入Bean的名字。
​	如果Bean实现了BeanClassLoaderAware接口，调用setBeanClassLoader()方法，传入ClassLoader对象的实例。
​	如果Bean实现了BeanFactoryAware接口，调用setBeanClassLoader()方法，传入ClassLoader对象的实例。
​	与上面的类似，如果实现了其他*Aware接口，就调用相应的方法。
​	如果有和加载这个Bean的Spring容器相关的BeanPostProcessor对象，执行postProcessBeforeInitialization()方法
​	如果Bean实现了InitializingBean接口，执行afterPropertiesSet()方法。
​	如果Bean在配置文件中的定义包含init-method属性，执行指定的方法。
​	如果有和加载这个Bean的Spring容器相关的BeanPostProcessor对象，执行postProcessAfterInitialization()方法
​	当要销毁Bean的时候，如果Bean实现了DisposableBean接口，执行destroy()方法。
​	当要销毁Bean的时候，如果Bean在配置文件中的定义包含destroy-method属性，执行指定的方法。
```



依赖注入：

	1. 获取当前对象中加了autowired的属性
	1. 根据ByType或者ByName获取bean，如果没有找到则会创建



循环依赖（针对单例Bean）：

​	在创建一个Bean1的时候，构造方法可能调用了其他Bean2，如果没有找到这个Bean1会发起创建Bean2流程，但是这个依赖的Bean2的构造方法也调用了这个Bean1，造成了循环依赖的现象



如何在Bean缓存池中查找Bean（针对单例Bean）:

​	单例bean只能有一个相同类型的bean，是错误的

![image-20220103164725142](/Users/lejinbo/Library/Application Support/typora-user-images/image-20220103164725142.png)

​	创建时如果存在多个相同类型的Bean，先根据Type，如果存在多个相同Type的就根据Name，如果存在多个且name对不上 则报错	



Spring AOP（面向切面编程）:

​	在不改变原有业务逻辑的情况下，增强横切逻辑代码，根本上解耦合，避免横切逻辑代码重复。

​	Pointcut:

​		对连接点进行拦截的定义（匹配规则定义 规定拦截哪些方法，对哪些方法进行处理），spring 有专门的表达式语言定义。

​	Advice:

		1. 前置通知 （前置增强）— before() 执行方法前通知
		1. 返回通知（返回增强）— afterReturn 方法正常结束返回后的通知
		1. 异常抛出通知（异常抛出增强）— afetrThrow()
		1. 最终通知 — after 无论方法是否发生异常，均会执行该通知。
		1. 环绕通知 — around 包围一个连接点（join point）的通知，如方法调用。这是最强大的一种通知类型。 环绕通知可以在方法调用前后完成自定义的行为。它也会选择是否继续执行连接点或直接返回它们自己的返回值或抛出异常来结束执行。



AOP的代理类详解：	![image-20220104101233426](/Users/lejinbo/Library/Application Support/typora-user-images/image-20220104101233426.png)





Bean的作用域（scope属性，注解方式 @Scope(value = ConfigurableBeanFactory.SCOPE_PROTOTYPE) ）：

```
	singletion:单例模式（默认值）：当一个 bean 的作用域为 singleton，那么Spring IoC容器中只会存在一个共享的 bean 实例，并且所有对 bean 的请求，只要 id 与该 bean定义相匹配，则只会返回bean的同一实例

​	prototype:每次请求就会创建一个Bean实例：当一个bean的作用域为 prototype，表示一个 bean 定义对应多个对象实例。 prototype 作用域的 bean 会导致在每次对该 bean 请求（将其注入到另一个 bean 中，或者以程序的方式		调用容器的 getBean() 方法）时都会创建一个新的 bean 实例。prototype 是原型类型，它在我们创建容器的时候并没有实例化，而是当我们获取bean的时候才会去创建一个对象，而且我们每次获取到的对象都不是同一个对象。		根据经验，对有状态的 bean 应该使用 prototype 作用域，而对无状态的 bean 则应该使用 singleton 作用域。 

​	request:每一次Http请求都会生成一个Bean实例，该Bean仅在当前request中有效。

​	session:每一个Http请求都会生成一个Bean实例，该Bean仅在当前requestSession中有效。

​	globalSession：仅在portlet的web应用中菜有意义，类似于session作用域。
```



单例Bean的线程安全问题：

​	主要是因为当多个线程操作同一个对象的时候存在资源竞争，常见的有两种解决方法：

	1. 在bean中尽量避免定义可变的成员变量
	1. 在类中定义一个ThreadLocal的成员变量，将需要的可变成员变量保存在threadLocal中





Spring事务：

​		1.编程式事务，在代码中硬编码，调用事务.commit()方法。可以选择在Aop中开启事务注解。

​		2.声明式事务，在配置文件中配置：基于XML的声明式事务和基于注解的声明式事务。

​		3.Spring事务的隔离级别：

​			1.使用后端数据库的默认级别。

​			2.读取未提交

​			3.读取已提交

​			4.可重复读。

​			5.可串行化

​		4.事务传播级别：

​			支持当前事务的情况：

​				1.PROPAGATION_REQUIRED： 如果当前存在事务，则加入该事务；如果当前没有事务，则创建一个新的事务。

​				2.PROPAGATION_SUPPORTS： 如果当前存在事务，则加入该事务；如果当前没有事务，则以非事务的方式继续运行。

​				3.PROPAGATION_MANDATORY： 如果当前存在事务，则加入该事务；如果当前没有事务，则抛出异常。（mandatory：强制性）

​			不支持当前事务的情况：

​				1.PROPAGATION_REQUIRES_NEW： 创建一个新的事务，如果当前存在事务，则把当前事务挂起。

​				2.PROPAGATION_NOT_SUPPORTED： 以非事务方式运行，如果当前存在事务，则把当前事务挂起。

​				3.PROPAGATION_NEVER： 以非事务方式运行，如果当前存在事务，则抛出异常。

​			其他情况：

​				1.PROPAGATION_NESTED： 如果当前存在事务，则创建一个事务作为当前事务的嵌套事务来运行；如果当前没有事务，则该取值等价于TransactionDefinition.PROPAGATION_REQUIRED。



![image-20220104102653921](/Users/lejinbo/Library/Application Support/typora-user-images/image-20220104102653921.png)



多个事务一起执行的情况下

![image-20220104103009179](/Users/lejinbo/Library/Application Support/typora-user-images/image-20220104103009179.png)

在这个userService中，test方法进行代理过后，执行a方法的时候相当于代理对象生成的普通对象执行a方法，类似于new UserService().a()执行，因此事务无效

![image-20220104103448810](/Users/lejinbo/Library/Application Support/typora-user-images/image-20220104103448810.png)



事务以Spring配置的为准，如果Spring设置的隔离级别数据库不支持，则采用数据库的隔离级别



SpringMVC:

​	服务端发起请求-》通过server-name获取tomcat中的server-》通过url获取mapping-》通过mapping获取DispatherServlet-》获取controllerBean-》