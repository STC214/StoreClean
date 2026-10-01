package de.robv.android.xposed;

/** Host-test fake only; never included in the module APK. */
public abstract class XC_MethodHook {
    protected void beforeHookedMethod(MethodHookParam param) throws Throwable {}

    protected void afterHookedMethod(MethodHookParam param) throws Throwable {}

    public final void probeBefore(MethodHookParam param) throws Throwable {
        beforeHookedMethod(param);
    }

    public static final class MethodHookParam {
        public Object[] args;
        public Object thisObject;
        public boolean skipped;
        public Object result;

        public void setResult(Object value) {
            result = value;
            skipped = true;
        }
    }
}
