package faultline.health;

import java.time.Duration;

public class HealthCheckClientTest {
    public static void main(String[] args) {
        HealthCheckClient checker = new HealthCheckClient(Duration.ofSeconds(1));

        assertTrue(checker.looksHealthy("{\"safe_to_operate\": true}"));
        assertTrue(checker.looksHealthy("{\"status\":\"ok\"}"));
        assertTrue(checker.looksHealthy("{\"healthy\":true}"));
        assertFalse(checker.looksHealthy("{\"safe_to_operate\": false}"));
        assertFalse(checker.looksHealthy("{}"));

        System.out.println("HealthCheckClientTest passed");
    }

    private static void assertTrue(boolean value) {
        if (!value) {
            throw new AssertionError("expected true");
        }
    }

    private static void assertFalse(boolean value) {
        if (value) {
            throw new AssertionError("expected false");
        }
    }
}
