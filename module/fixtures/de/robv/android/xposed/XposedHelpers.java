package de.robv.android.xposed;

/** Host-test reflection adapter, not a replacement shipped to Android. */
public final class XposedHelpers {
    private XposedHelpers() {}

    public static Object callMethod(Object receiver, String name, Object... args) {
        try {
            java.lang.reflect.Method method = receiver.getClass().getMethod(name);
            return method.invoke(receiver, args);
        } catch (ReflectiveOperationException failure) {
            throw new AssertionError(failure);
        }
    }
}
