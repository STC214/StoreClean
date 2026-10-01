package io.github.storeclean;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/** Version-gated, read-only overrides. A null result always means pass-through. */
public final class Policy {
    public static final String TARGET = "com.xiaomi.market";
    public static final String SECURITY_KEY = "pref_key_app_security_check";
    public static final Map<String, Boolean> PREFERENCES;
    public static final Map<String, Boolean> GETTERS;

    static {
        Map<String, Boolean> preferences = new LinkedHashMap<>();
        String[] off = {
            "pref_key_short_play", "pref_key_h5_topic", "pref_key_global_net",
            "pref_key_quick_app", "pref_key_cloud_game_icon", "pref_key_support_game_lottery",
            "pref_key_mini_game", "pref_key_mini_program_switch", "pref_key_need_welfare",
            "pref_key_child_mode_setting", "pref_key_orchard"
        };
        for (String key : off) {
            preferences.put(key, false);
        }
        String[] on = {
            "pref_key_phone_clean", "pref_key_app_lock", "pref_key_permission_management",
            "pref_key_milink_service"
        };
        for (String key : on) {
            preferences.put(key, true);
        }
        PREFERENCES = Collections.unmodifiableMap(preferences);

        Map<String, Boolean> getters = new LinkedHashMap<>();
        String[] disabled = {
            "isH5TopicEnabled", "isGlobalNetEnabled", "isQuickAppEnabled",
            "needAutoAddCloudGameIcon", "needAutoAddCloudGameIconForCloud", "supportGameLottery",
            "isQuickAppGameEnabled", "isMiniProgramRevisitEnabled", "isChildModeSettingCheck",
            "isOrchardEnabled"
        };
        for (String method : disabled) {
            getters.put(method, false);
        }
        String[] enabled = {
            "needBlockWelfare", "needPhoneClean", "isAppLockCheck",
            "isPermissionManagementCheck", "isMilinkServiceCheck"
        };
        for (String method : enabled) {
            getters.put(method, true);
        }
        GETTERS = Collections.unmodifiableMap(getters);
    }

    private Policy() {}

    public static boolean supports(String name, long code) {
        return ("4.126.10".equals(name) && code == 40007640L)
                || ("4.126.s.1".equals(name) && code == 40007621L)
                || ("4.126.s.2".equals(name) && code == 40007622L);
    }

    public static Boolean preference(String key) {
        return PREFERENCES.get(key);
    }
}
