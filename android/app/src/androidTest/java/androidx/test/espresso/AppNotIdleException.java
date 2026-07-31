package androidx.test.espresso;

public class AppNotIdleException extends RuntimeException {
    public AppNotIdleException(String message) {
        super(message);
    }
}
