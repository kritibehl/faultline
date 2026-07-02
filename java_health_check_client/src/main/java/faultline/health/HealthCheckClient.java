package faultline.health;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class HealthCheckClient {
    private final HttpClient client;
    private final Duration timeout;

    public HealthCheckClient(Duration timeout) {
        this.timeout = timeout;
        this.client = HttpClient.newBuilder()
                .connectTimeout(timeout)
                .build();
    }

    public boolean isHealthy(String url) throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(timeout)
                .GET()
                .build();

        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());

        return response.statusCode() >= 200
                && response.statusCode() < 300
                && looksHealthy(response.body());
    }

    public boolean looksHealthy(String json) {
        if (json == null) {
            return false;
        }

        String normalized = json.replace(" ", "").toLowerCase();

        return normalized.contains("\"safe_to_operate\":true")
                || normalized.contains("\"status\":\"ok\"")
                || normalized.contains("\"healthy\":true");
    }

    public static void main(String[] args) throws Exception {
        String url = args.length > 0 ? args[0] : "http://localhost:8088/health";
        HealthCheckClient checker = new HealthCheckClient(Duration.ofSeconds(2));

        boolean healthy = checker.isHealthy(url);

        System.out.println("health_url=" + url);
        System.out.println("healthy=" + healthy);

        if (!healthy) {
            System.exit(1);
        }
    }
}
