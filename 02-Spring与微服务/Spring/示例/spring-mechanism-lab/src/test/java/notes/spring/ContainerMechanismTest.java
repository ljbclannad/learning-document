package notes.spring;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.FactoryBean;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ContainerMechanismTest {
    @Test
    void definitionProcessingPrecedesCreationAndDependencyIsRegistered() {
        List<String> calls = new ArrayList<>();
        try (var context = new AnnotationConfigApplicationContext()) {
            context.getBeanFactory().registerSingleton("calls", new EventLog(calls));
            context.register(LifecycleConfig.class);
            context.refresh();
            assertThat(calls).containsExactly("定义处理", "构造", "初始化前", "初始化", "初始化后");
            assertThat(context.getBeanFactory().getDependenciesForBean("tracked"))
                    .contains("calls");
            assertThat(context.getBeanFactory().getDependentBeans("calls"))
                    .contains("tracked");
        }
        assertThat(calls).endsWith("销毁");
    }

    @Configuration(proxyBeanMethods = false)
    static class LifecycleConfig {
        @Bean
        static BeanFactoryPostProcessor definitionObserver() {
            return factory -> {
                // 测试先注册的观察器实例不需要创建，不会提前触发业务 Bean。
                EventLog log = (EventLog) factory.getSingleton("calls");
                log.calls.add("定义处理");
            };
        }

        @Bean
        static BeanPostProcessor observer() {
            return new BeanPostProcessor() {
                @Override
                public Object postProcessBeforeInitialization(Object bean, String name) {
                    if (bean instanceof Tracked tracked) tracked.calls.add("初始化前");
                    return bean;
                }
                @Override
                public Object postProcessAfterInitialization(Object bean, String name) {
                    if (bean instanceof Tracked tracked) tracked.calls.add("初始化后");
                    return bean;
                }
            };
        }

        @Bean
        Tracked tracked(EventLog log) { return new Tracked(log.calls); }
    }

    record EventLog(List<String> calls) {}

    static class Tracked implements InitializingBean, DisposableBean {
        final List<String> calls;
        Tracked(List<String> calls) { this.calls = calls; calls.add("构造"); }
        @Override public void afterPropertiesSet() { calls.add("初始化"); }
        @Override public void destroy() { calls.add("销毁"); }
    }

    @Test
    void prototypeInjectedOnceDiffersFromProviderLookup() {
        try (var context = new AnnotationConfigApplicationContext(ScopeConfig.class)) {
            Holder holder = context.getBean(Holder.class);
            assertThat(holder.fixed).isSameAs(context.getBean(Holder.class).fixed);
            assertThat(holder.provider.getObject()).isNotSameAs(holder.provider.getObject());
        }
    }
    static class Scratch {}
    record Holder(Scratch fixed, ObjectProvider<Scratch> provider) {}
    @Configuration(proxyBeanMethods = false)
    static class ScopeConfig {
        @Bean @Scope("prototype") Scratch scratch() { return new Scratch(); }
        @Bean Holder holder(Scratch fixed, ObjectProvider<Scratch> provider) {
            return new Holder(fixed, provider);
        }
    }

    @Test
    void liteConfigurationDirectCallCreatesAnotherObject() {
        try (var full = new AnnotationConfigApplicationContext(FullConfig.class);
             var lite = new AnnotationConfigApplicationContext(LiteConfig.class)) {
            assertThat(full.getBean("chosen")).isSameAs(full.getBean("item"));
            assertThat(lite.getBean("chosen")).isNotSameAs(lite.getBean("item"));
        }
    }
    @Configuration
    static class FullConfig {
        @Bean Object item() { return new Object(); }
        @Bean Object chosen() { return item(); }
    }
    @Configuration(proxyBeanMethods = false)
    static class LiteConfig {
        @Bean Object item() { return new Object(); }
        @Bean Object chosen() { return item(); }
    }

    @Test
    void fieldCycleRequiresExplicitContainerPermission() {
        try (var allowed = new AnnotationConfigApplicationContext()) {
            allowed.getDefaultListableBeanFactory().setAllowCircularReferences(true);
            allowed.register(A.class, B.class);
            allowed.refresh();
            assertThat(allowed.getBean(A.class).b.a).isSameAs(allowed.getBean(A.class));
        }
        try (var denied = new AnnotationConfigApplicationContext()) {
            denied.getDefaultListableBeanFactory().setAllowCircularReferences(false);
            denied.register(A.class, B.class);
            assertThatThrownBy(denied::refresh).hasStackTraceContaining("currently in creation");
        }
    }
    static class A { @Autowired B b; }
    static class B { @Autowired A a; }

    @Test
    void factoryProductDoesNotAutomaticallyReceiveDestroyCallback() {
        Product product = new Product();
        Maker maker = new Maker(product);
        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean("made", Maker.class, () -> maker);
            context.refresh();
            assertThat(context.getBean("made")).isSameAs(product);
            assertThat(context.getBean("&made")).isSameAs(maker);
        }
        assertThat(maker.destroyed).isTrue();
        assertThat(product.destroyed).isFalse();
    }
    static class Product implements DisposableBean {
        boolean destroyed;
        @Override public void destroy() { destroyed = true; }
    }
    static class Maker implements FactoryBean<Product>, DisposableBean {
        final Product product;
        boolean destroyed;
        Maker(Product product) { this.product = product; }
        @Override public Product getObject() { return product; }
        @Override public Class<?> getObjectType() { return Product.class; }
        @Override public boolean isSingleton() { return true; }
        @Override public void destroy() { destroyed = true; }
    }
}
