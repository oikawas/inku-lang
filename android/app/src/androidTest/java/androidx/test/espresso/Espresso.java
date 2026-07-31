package androidx.test.espresso;

public final class Espresso {
    private Espresso() {}

    public static void onIdle() {
        // Safe no-op for Compose UI testing on Android 15
    }

    public static boolean registerIdlingResources(IdlingResource... resources) {
        return true;
    }

    public static boolean unregisterIdlingResources(IdlingResource... resources) {
        return true;
    }
}
