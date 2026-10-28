package notes.spring;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationTest {
    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(GuardAutoConfiguration.class));

    @Test void propertyDefaultDoesNotAutomaticallySatisfyCondition() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(GuardProperties.class).doesNotHaveBean(GuardStore.class);
            assertThat(context.getBean(GuardProperties.class).type()).isEqualTo("memory");
        });
    }
    @Test void explicitPropertyRegistersDefaultAndBindsDuration() {
        runner.withPropertyValues("action.guard.store.type=memory", "action.guard.store.timeout=350ms")
                .run(context -> {
                    assertThat(context).hasSingleBean(GuardStore.class);
                    assertThat(context.getBean(GuardStore.class).kind()).isEqualTo("内存");
                    assertThat(context.getBean(GuardProperties.class).timeout()).isEqualTo(Duration.ofMillis(350));
                });
    }
    @Test void differentlyNamedUserBeanMakesDefaultBackOff() {
        runner.withPropertyValues("action.guard.store.type=memory")
                .withUserConfiguration(UserConfig.class).run(context -> {
                    assertThat(context).hasSingleBean(GuardStore.class).doesNotHaveBean("defaultStore");
                    assertThat(context.getBean(GuardStore.class).kind()).isEqualTo("用户实现");
                });
    }
    @Test void nonMatchingPropertySkipsDefault() {
        runner.withPropertyValues("action.guard.store.type=jdbc")
                .run(context -> assertThat(context).doesNotHaveBean(GuardStore.class));
    }
    interface GuardStore { String kind(); }
    @ConfigurationProperties("action.guard.store")
    record GuardProperties(@DefaultValue("memory") String type,
                           @DefaultValue("2s") Duration timeout) {}
    @AutoConfiguration
    @EnableConfigurationProperties(GuardProperties.class)
    static class GuardAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(GuardStore.class)
        @ConditionalOnProperty(prefix = "action.guard.store", name = "type", havingValue = "memory")
        GuardStore defaultStore() { return () -> "内存"; }
    }
    @Configuration(proxyBeanMethods = false)
    static class UserConfig {
        @Bean GuardStore customStore() { return () -> "用户实现"; }
    }
}
