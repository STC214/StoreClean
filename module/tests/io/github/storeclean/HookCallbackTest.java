package io.github.storeclean;

import android.view.View;
import de.robv.android.xposed.XC_MethodHook;
import java.lang.reflect.Method;
import java.util.Map;

/** Exercises production callbacks using explicit host fakes, not a real Xposed engine. */
public final class HookCallbackTest {
    public static void main(String[] args) throws Throwable {
        XC_MethodHook read = callback("preferenceRead", new Class<?>[0]);
        XC_MethodHook write = callback("preferenceWrite", new Class<?>[] {boolean.class}, false);
        XC_MethodHook sync = callback("preferenceWrite", new Class<?>[] {boolean.class}, true);
        for (Map.Entry<String, Boolean> entry : Policy.PREFERENCES.entrySet()) {
            XC_MethodHook.MethodHookParam param = probe(read, entry.getKey(), !entry.getValue(), null);
            require(param.skipped && entry.getValue().equals(param.result), "read override");
            param = probe(write, entry.getKey(), !entry.getValue(), null);
            require(param.skipped && param.result == null, "skip void storage writer");
            param = probe(sync, entry.getKey(), !entry.getValue(), null);
            require(param.skipped && Boolean.TRUE.equals(param.result), "skip sync storage writer");
            Method desired = StoreHooks.class.getDeclaredMethod("desiredForPreference", Object.class);
            desired.setAccessible(true);
            require(entry.getValue().equals(desired.invoke(null, new Preference(entry.getKey()))), "preference key lookup");
        }
        for (String excluded : new String[] {Policy.SECURITY_KEY, "unrelated", null}) {
            for (XC_MethodHook hook : new XC_MethodHook[] {read, write, sync}) {
                require(!probe(hook, excluded, false, null).skipped, "excluded call must reach original");
                require(!probe(hook, excluded, true, null).skipped, "both excluded values pass through");
            }
        }
        for (Object constant : new Object[] {false, true, null}) {
            XC_MethodHook hook = callback("constant", new Class<?>[] {Object.class}, constant);
            XC_MethodHook.MethodHookParam param = probe(hook);
            require(param.skipped && java.util.Objects.equals(param.result, constant), "constant result");
        }
        View entrance = new View();
        Method hide = StoreHooks.class.getDeclaredMethod("hideEntrance", Object.class);
        hide.setAccessible(true);
        hide.invoke(null, entrance);
        require(entrance.visibility == View.GONE && !entrance.enabled
                && !entrance.clickable && entrance.listener == null, "entrance state/click suppression");
        hide.invoke(null, new Object());
        Method resolver = StoreHooks.class.getDeclaredMethod("resolveOrchardMethods", Class.class);
        resolver.setAccessible(true);
        require(((java.util.List<?>) resolver.invoke(null, OldSdk.class)).size() == 5, "canonical old SDK plan");
        require(((java.util.List<?>) resolver.invoke(null, NewSdk.class)).size() == 8, "seven launches plus H5");
        Method validator = StoreHooks.class.getDeclaredMethod("validateOrchardMethod", Method.class);
        validator.setAccessible(true);
        for (Class<?> bad : new Class<?>[] {WrongArgument.class, WrongReturn.class, WrongStatic.class,
                WrongH5.class, WrongCallback.class}) {
            try {
                validator.invoke(null, bad.getDeclaredMethods()[0]);
                throw new AssertionError("Malformed orchard contract accepted: " + bad);
            } catch (java.lang.reflect.InvocationTargetException expected) {
                require(expected.getCause() instanceof IllegalStateException, "malformed launch rejection");
            }
        }
        try {
            resolver.invoke(null, MissingCanonical.class);
            throw new AssertionError("Noncanonical overloads accepted");
        } catch (java.lang.reflect.InvocationTargetException expected) {
            require(expected.getCause() instanceof NoSuchMethodException, "missing canonical rejection");
        }
        System.out.println("PASS production callbacks with host fakes: 15 reads/writes, exclusions, constant skips, entrance hidden; 5/8 SDK methods resolved; malformed/missing contracts rejected");
    }

    private static XC_MethodHook callback(String name, Class<?>[] types, Object... args)
            throws Exception {
        Method method = StoreHooks.class.getDeclaredMethod(name, types);
        method.setAccessible(true);
        return (XC_MethodHook) method.invoke(null, args);
    }

    private static XC_MethodHook.MethodHookParam probe(XC_MethodHook hook, Object... args)
            throws Throwable {
        XC_MethodHook.MethodHookParam param = new XC_MethodHook.MethodHookParam();
        param.args = args;
        hook.probeBefore(param);
        return param;
    }

    private static void require(boolean value, String label) {
        if (!value) {
            throw new AssertionError(label);
        }
    }

    public static final class Preference {
        private final String key;

        Preference(String key) {
            this.key = key;
        }

        public String getKey() {
            return key;
        }
    }

    public static class OldSdk {
        public void launchOrchard(android.app.Activity a) {}
        public void launchOrchard(android.app.Activity a, String b) {}
        public void launchOrchard(android.app.Activity a, String b, String c) {}
        public void launchOrchard(android.app.Activity a, String b, String c, Integer d) {}
        public void launchOrchard(android.app.Activity a, String b, String c, Integer d, Map<?, ?> e) {}
    }

    public static class NewSdk {
        public void launchOrchard(android.app.Activity a) {}
        public void launchOrchard(android.app.Activity a, String b) {}
        public void launchOrchard(android.app.Activity a, String b, String c) {}
        public void launchOrchard(android.app.Activity a, String b, String c, Integer d) {}
        public void launchOrchard(android.app.Activity a, String b, String c, Integer d, Map<?, ?> e) {}
        public void launchOrchard(android.app.Activity a, String b, String c, Integer d, Map<?, ?> e, boolean f) {}
        public void launchOrchard(android.app.Activity a, String b, String c, Integer d, Map<?, ?> e, boolean f, Runnable g) {}
        public void launchOrchardH5$app_release(android.app.Activity a, String b, String c, Integer d, Map<?, ?> e) {}
    }

    public static class WrongArgument { public void launchOrchard(android.app.Activity a, int b) {} }
    public static class WrongReturn { public String launchOrchard(android.app.Activity a) { return ""; } }
    public static class WrongStatic { public static void launchOrchard(android.app.Activity a) {} }
    public static class WrongH5 { public void launchOrchardH5$app_release(android.app.Activity a) {} }
    public static class WrongCallback {
        public void launchOrchard(android.app.Activity a, String b, String c, Integer d, Map<?, ?> e, boolean f, int g) {}
    }
    public static class MissingCanonical { public void launchOrchard(android.app.Activity a, int b) {} }
}
