package io.github.storeclean;

import android.app.Application;
import android.content.Context;
import android.content.pm.PackageInfo;
import android.view.View;
import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** Only registered package versions are touched; all preference overrides are read-only. */
public final class StoreHooks implements IXposedHookLoadPackage {
    private static final String PREFIX = "[StoreClean] ";
    private boolean initialized;

    @Override
    public void handleLoadPackage(final XC_LoadPackage.LoadPackageParam packageParam) {
        if (!Policy.TARGET.equals(packageParam.packageName)) {
            return;
        }
        XposedHelpers.findAndHookMethod(Application.class, "attach", Context.class,
                new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        initialize((Context) param.args[0], packageParam.classLoader);
                    }
                });
    }

    private synchronized void initialize(Context context, ClassLoader loader) {
        if (initialized) {
            return;
        }
        initialized = true;
        List<XC_MethodHook.Unhook> installed = new ArrayList<>();
        try {
            PackageInfo info = context.getPackageManager().getPackageInfo(Policy.TARGET, 0);
            if (!Policy.supports(info.versionName, info.versionCode)) {
                XposedBridge.log(PREFIX + "unsupported version: " + info.versionName);
                return;
            }
            // Resolve the complete plan before installing: missing mandatory targets fail closed.
            List<Binding> plan = resolve(loader);
            for (Binding binding : plan) {
                installed.add(XposedBridge.hookMethod(binding.method, binding.callback));
            }
            XposedBridge.log(PREFIX + "active version=" + info.versionName
                    + " hooks=" + installed.size() + " controlled writes=blocked");
        } catch (Throwable failure) {
            for (XC_MethodHook.Unhook hook : installed) {
                try {
                    hook.unhook();
                } catch (Throwable cleanupFailure) {
                    XposedBridge.log(PREFIX + "unhook failure: " + cleanupFailure);
                }
            }
            XposedBridge.log(PREFIX + "initialization aborted: " + failure);
        }
    }

    private List<Binding> resolve(ClassLoader loader) throws Exception {
        List<Binding> plan = new ArrayList<>();
        Class<?> prefs = Class.forName("com.xiaomi.market.util.PrefUtils", false, loader);
        Class<?> files = Class.forName("[Lcom.xiaomi.market.util.PrefUtils$PrefFile;", false, loader);
        add(plan, prefs.getDeclaredMethod("getBoolean", String.class, boolean.class, files),
                preferenceRead());
        add(plan, prefs.getDeclaredMethod("setBoolean", String.class, boolean.class, files),
                preferenceWrite(false));
        add(plan, prefs.getDeclaredMethod("setBooleanSync", String.class, boolean.class, files),
                preferenceWrite(true));

        Class<?> settings = Class.forName("com.xiaomi.market.util.SettingsUtils", false, loader);
        for (Map.Entry<String, Boolean> entry : Policy.GETTERS.entrySet()) {
            Method method = settings.getDeclaredMethod(entry.getKey());
            requireReturn(method, boolean.class);
            add(plan, method, constant(entry.getValue()));
        }
        Class<?> orchard = Class.forName("com.xiaomi.market.util.OrchardEntranceManager", false, loader);
        add(plan, orchard.getDeclaredMethod("isOpen"), constant(false));
        add(plan, orchard.getDeclaredMethod("reopen"), constant(null));
        Class<?> sdk = Class.forName("com.xiaomi.market.incentive.orchard.OrchardSdkHelper", false, loader);
        int launches = 0;
        for (Method method : sdk.getDeclaredMethods()) {
            if (method.getName().equals("launchOrchard")) {
                requireReturn(method, void.class);
                add(plan, method, constant(null));
                launches++;
            }
        }
        if (launches != 5) {
            throw new IllegalStateException("Expected five orchard launch overloads, got " + launches);
        }
        Class<?> manager = Class.forName("com.xiaomi.market.util.EntranceManager", false, loader);
        add(plan, manager.getDeclaredMethod("getEntranceConfig"), constant(null));
        add(plan, manager.getDeclaredMethod("needShowAnimation"), constant(false));
        Class<?> entrance = Class.forName("com.xiaomi.market.ui.entrance.EntranceView", false, loader);
        add(plan, entrance.getDeclaredMethod("bindView", Context.class, String.class),
                new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        hideEntrance(param.thisObject);
                        param.setResult(null);
                    }
                });
        add(plan, entrance.getDeclaredMethod("onFinishInflate"), new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                hideEntrance(param.thisObject);
            }
        });

        Class<?> preference = Class.forName("androidx.preference.Preference", false, loader);
        add(plan, preference.getDeclaredMethod("getPersistedBoolean", boolean.class),
                new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        Boolean desired = desiredForPreference(param.thisObject);
                        if (desired != null) {
                            param.setResult(desired);
                        }
                    }
                });
        add(plan, preference.getDeclaredMethod("persistBoolean", boolean.class),
                new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        if (desiredForPreference(param.thisObject) != null) {
                            param.setResult(true);
                        }
                    }
                });
        Class<?> state = Class.forName("androidx.preference.TwoStatePreference", false, loader);
        add(plan, state.getDeclaredMethod("setChecked", boolean.class), new XC_MethodHook() {
            @Override
            protected void beforeHookedMethod(MethodHookParam param) {
                Boolean desired = desiredForPreference(param.thisObject);
                if (desired != null) {
                    param.args[0] = desired;
                }
            }
        });

        Class<?> fragment = Class.forName(
                "com.xiaomi.market.business_ui.settings.function.FunctionSettingsFragment", false, loader);
        add(plan, fragment.getDeclaredMethod("onPreferenceChange", preference, Object.class),
                new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        if (desiredForPreference(param.args[0]) != null) {
                            param.setResult(false);
                        }
                    }
                });
        add(plan, fragment.getDeclaredMethod("onCreatePreferences", android.os.Bundle.class, String.class),
                new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        for (Map.Entry<String, Boolean> entry : Policy.PREFERENCES.entrySet()) {
                            Object item = XposedHelpers.callMethod(
                                    param.thisObject, "findPreference", entry.getKey());
                            if (item != null) {
                                XposedHelpers.callMethod(item, "setChecked", entry.getValue());
                                XposedHelpers.callMethod(item, "setEnabled", false);
                            }
                        }
                    }
                });
        return plan;
    }

    private static XC_MethodHook preferenceRead() {
        return new XC_MethodHook() {
            @Override
            protected void beforeHookedMethod(MethodHookParam param) {
                Boolean desired = Policy.preference((String) param.args[0]);
                if (desired != null) {
                    param.setResult(desired);
                }
            }
        };
    }

    private static XC_MethodHook preferenceWrite(final boolean synchronous) {
        return new XC_MethodHook() {
            @Override
            protected void beforeHookedMethod(MethodHookParam param) {
                if (Policy.preference((String) param.args[0]) != null) {
                    param.setResult(synchronous ? Boolean.TRUE : null);
                }
            }
        };
    }

    private static XC_MethodHook constant(final Object value) {
        return new XC_MethodHook() {
            @Override
            protected void beforeHookedMethod(MethodHookParam param) {
                param.setResult(value);
            }
        };
    }

    private static Boolean desiredForPreference(Object preference) {
        if (preference == null) {
            return null;
        }
        return Policy.preference((String) XposedHelpers.callMethod(preference, "getKey"));
    }

    private static void hideEntrance(Object instance) {
        if (instance instanceof View) {
            View view = (View) instance;
            view.setOnClickListener(null);
            view.setClickable(false);
            view.setEnabled(false);
            view.setVisibility(View.GONE);
        }
    }

    private static void add(List<Binding> plan, Method method, XC_MethodHook callback) {
        method.setAccessible(true);
        plan.add(new Binding(method, callback));
    }

    private static void requireReturn(Method method, Class<?> expected) {
        if (method.getReturnType() != expected) {
            throw new IllegalStateException("Unexpected return type: " + method);
        }
    }

    private static final class Binding {
        final Method method;
        final XC_MethodHook callback;

        Binding(Method method, XC_MethodHook callback) {
            this.method = method;
            this.callback = callback;
        }
    }
}
