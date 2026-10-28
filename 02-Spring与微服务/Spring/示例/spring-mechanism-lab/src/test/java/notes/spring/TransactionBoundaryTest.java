package notes.spring;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import javax.sql.DataSource;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class TransactionBoundaryTest {
    AnnotationConfigApplicationContext context;
    JdbcTemplate jdbc;
    Work work;
    @BeforeEach void open() {
        context = new AnnotationConfigApplicationContext(Config.class);
        jdbc = context.getBean(JdbcTemplate.class);
        jdbc.execute("create table records(id int primary key)");
        work = context.getBean(Work.class);
    }
    @AfterEach void close() {
        try { jdbc.execute("SHUTDOWN"); } finally { context.close(); }
    }
    int count() { return jdbc.queryForObject("select count(*) from records", Integer.class); }

    @Test void externalCallRollsBackButSelfCallDoesNotStartTransaction() {
        assertThatThrownBy(() -> work.fail(1)).isInstanceOf(IllegalStateException.class);
        assertThat(count()).isZero();
        assertThatThrownBy(() -> work.selfWithoutTransaction(2)).isInstanceOf(IllegalStateException.class);
        assertThat(count()).isEqualTo(1);
    }
    @Test void selfCallStillRunsInsideExistingOuterTransaction() {
        assertThatThrownBy(() -> work.outerSelf(1)).isInstanceOf(IllegalStateException.class);
        assertThat(count()).isZero();
    }
    @Test void caughtRequiredFailureMarksSharedTransactionRollbackOnly() {
        assertThatThrownBy(work::catchRequired).isInstanceOf(UnexpectedRollbackException.class);
        assertThat(count()).isZero();
    }
    @Test void requiresNewCommitSurvivesOuterRollback() {
        assertThatThrownBy(work::independentThenFail).isInstanceOf(IllegalStateException.class);
        assertThat(jdbc.queryForList("select id from records", Integer.class)).containsExactly(2);
    }
    @Test void nestedRollbackUsesSavepointWhileOuterCanCommit() {
        work.catchNested();
        assertThat(jdbc.queryForList("select id from records order by id", Integer.class))
                .containsExactly(1, 3);
    }
    @Test void transactionalEventNeedsCommitAndActiveTransaction() {
        Listener listener = context.getBean(Listener.class);
        context.publishEvent(new Changed("无事务"));
        work.publish(false);
        assertThatThrownBy(() -> work.publish(true)).isInstanceOf(IllegalStateException.class);
        assertThat(listener.seen).containsExactly("已提交");
    }
    @Test void commitCallbackRunsBeforeConnectionResourceCleanup() {
        DataSource source = context.getBean(DataSource.class);
        List<Boolean> bound = new ArrayList<>();
        new TransactionTemplate(context.getBean(PlatformTransactionManager.class))
                .executeWithoutResult(status -> TransactionSynchronizationManager.registerSynchronization(
                        new TransactionSynchronization() {
                            @Override public void afterCommit() {
                                bound.add(TransactionSynchronizationManager.hasResource(source));
                            }
                        }));
        assertThat(bound).containsExactly(true);
        assertThat(TransactionSynchronizationManager.hasResource(source)).isFalse();
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    static class Config {
        @Bean DataSource source() {
            return new DriverManagerDataSource("jdbc:h2:mem:" + UUID.randomUUID() + ";DB_CLOSE_DELAY=-1", "sa", "");
        }
        @Bean PlatformTransactionManager transactionManager(DataSource source) {
            return new DataSourceTransactionManager(source);
        }
        @Bean JdbcTemplate jdbc(DataSource source) { return new JdbcTemplate(source); }
        @Bean Inner inner(JdbcTemplate jdbc) { return new Inner(jdbc); }
        @Bean Work work(JdbcTemplate jdbc, Inner inner, ApplicationEventPublisher publisher) {
            return new Work(jdbc, inner, publisher);
        }
        @Bean Listener listener() { return new Listener(); }
    }
    public static class Inner {
        final JdbcTemplate jdbc;
        Inner(JdbcTemplate jdbc) { this.jdbc = jdbc; }
        @Transactional public void requiredFail() { jdbc.update("insert into records values(2)"); fail(); }
        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void independent() { jdbc.update("insert into records values(2)"); }
        @Transactional(propagation = Propagation.NESTED)
        public void nestedFail() { jdbc.update("insert into records values(2)"); fail(); }
        private void fail() { throw new IllegalStateException("模拟业务失败"); }
    }
    public static class Work {
        final JdbcTemplate jdbc;
        final Inner inner;
        final ApplicationEventPublisher publisher;
        Work(JdbcTemplate jdbc, Inner inner, ApplicationEventPublisher publisher) {
            this.jdbc = jdbc; this.inner = inner; this.publisher = publisher;
        }
        @Transactional public void fail(int id) {
            jdbc.update("insert into records values(?)", id);
            throw new IllegalStateException("模拟业务失败");
        }
        public void selfWithoutTransaction(int id) { fail(id); }
        @Transactional public void outerSelf(int id) { fail(id); }
        @Transactional public void catchRequired() {
            jdbc.update("insert into records values(1)");
            try { inner.requiredFail(); } catch (IllegalStateException expected) { /* 验证吞异常边界。 */ }
        }
        @Transactional public void independentThenFail() {
            jdbc.update("insert into records values(1)");
            inner.independent();
            throw new IllegalStateException("外层回滚");
        }
        @Transactional public void catchNested() {
            jdbc.update("insert into records values(1)");
            try { inner.nestedFail(); } catch (IllegalStateException expected) { /* 允许局部回滚。 */ }
            jdbc.update("insert into records values(3)");
        }
        @Transactional public void publish(boolean fail) {
            publisher.publishEvent(new Changed(fail ? "已回滚" : "已提交"));
            if (fail) throw new IllegalStateException("回滚事件所在事务");
        }
    }
    record Changed(String value) {}
    public static class Listener {
        final List<String> seen = new ArrayList<>();
        @TransactionalEventListener public void on(Changed event) { seen.add(event.value()); }
    }
}
