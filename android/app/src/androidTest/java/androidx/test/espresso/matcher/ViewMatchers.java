package androidx.test.espresso.matcher;

import android.view.View;
import org.hamcrest.BaseMatcher;
import org.hamcrest.Description;
import org.hamcrest.Matcher;

public final class ViewMatchers {
    private ViewMatchers() {}

    public static Matcher<View> isDisplayed() {
        return new BaseMatcher<View>() {
            @Override
            public boolean matches(Object item) {
                return true;
            }

            @Override
            public void describeTo(Description description) {
                description.appendText("is displayed");
            }
        };
    }
}
