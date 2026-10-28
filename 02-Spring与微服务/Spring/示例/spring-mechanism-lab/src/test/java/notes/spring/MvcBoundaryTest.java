package notes.spring;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.Callable;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.util.ContentCachingRequestWrapper;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class MvcBoundaryTest {
    LocalValidatorFactoryBean validator;
    MockMvc mvc;
    @BeforeEach void open() {
        validator = new LocalValidatorFactoryBean();
        validator.afterPropertiesSet();
        mvc = MockMvcBuilders.standaloneSetup(new ReportController())
                .setControllerAdvice(new ApiErrors()).setValidator(validator)
                .setAsyncRequestTimeout(3000).build();
    }
    @AfterEach void close() { validator.close(); }

    @Test void validBodyIsConvertedToDto() throws Exception {
        mvc.perform(post("/reports").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"patientId\":\"p-1\"}"))
                .andExpect(status().isOk()).andExpect(jsonPath("patientId").value("p-1"));
    }
    @Test void invalidBodyFailsBeforeControllerWork() throws Exception {
        mvc.perform(post("/reports").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"patientId\":\"\"}"))
                .andExpect(status().isBadRequest());
    }
    @Test void malformedJsonAndUnsupportedMediaAreDifferentFailures() throws Exception {
        mvc.perform(post("/reports").contentType(MediaType.APPLICATION_JSON).content("{"))
                .andExpect(status().isBadRequest());
        mvc.perform(post("/reports").contentType(MediaType.TEXT_PLAIN).content("p-1"))
                .andExpect(status().isUnsupportedMediaType());
    }
    @Test void mvcAsyncExceptionIsResolvedAfterRedispatch() throws Exception {
        MvcResult started = mvc.perform(get("/reports/async"))
                .andExpect(request().asyncStarted()).andReturn();
        started.getAsyncResult(3000);
        mvc.perform(asyncDispatch(started)).andExpect(status().isForbidden())
                .andExpect(jsonPath("detail").value("无权读取该报告"));
    }
    @Test void cachingWrapperObservesReadsButDoesNotReplayInputStream() throws Exception {
        MockHttpServletRequest raw = new MockHttpServletRequest();
        raw.setContent("body".getBytes(StandardCharsets.UTF_8));
        ContentCachingRequestWrapper wrapper = new ContentCachingRequestWrapper(raw, 32);
        assertThat(wrapper.getContentAsByteArray()).isEmpty();
        assertThat(wrapper.getInputStream().readAllBytes()).isEqualTo(raw.getContentAsByteArray());
        assertThat(wrapper.getContentAsByteArray()).isEqualTo(raw.getContentAsByteArray());
        assertThat(wrapper.getInputStream().readAllBytes()).isEmpty();
    }
    record Query(@NotBlank String patientId) {}
    @RestController
    static class ReportController {
        @PostMapping(value = "/reports", consumes = "application/json")
        Map<String, String> read(@Valid @RequestBody Query query) {
            return Map.of("patientId", query.patientId());
        }
        @GetMapping("/reports/async")
        Callable<String> async() { return () -> { throw new NoAccess(); }; }
    }
    static class NoAccess extends RuntimeException {}
    @RestControllerAdvice
    static class ApiErrors {
        @ExceptionHandler(NoAccess.class)
        ProblemDetail denied() {
            return ProblemDetail.forStatusAndDetail(HttpStatus.FORBIDDEN, "无权读取该报告");
        }
    }
}
