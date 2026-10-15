package io.github.storeclean;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.List;
import java.util.HashSet;
import java.util.Set;

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
                || ("4.126.s.2".equals(name) && code == 40007622L)
                || ("4.127.11".equals(name) && code == 40007661L);
    }

    /** Candidate only: the caller must validate the menu and every hook before registration. */
    public static boolean allowsStructuralProbe(String name, long code) {
        if (name == null || code < 40000000L || code >= 50000000L) {
            return false;
        }
        for (String known : new String[] {"4.126.10", "4.126.s.1", "4.126.s.2", "4.127.11"}) {
            if (known.equals(name)) {
                return false; // A known name with the wrong code must not bypass its gate.
            }
        }
        return name.matches("4\\.\\d+\\.(?:s\\.)?\\d+");
    }

    public static int settingsGroup(String key) {
        if (SECURITY_KEY.equals(key) || Boolean.TRUE.equals(preference(key))) {
            return 2;
        }
        if ("pref_key_short_play".equals(key) || "pref_key_h5_topic".equals(key)
                || "pref_key_global_net".equals(key) || "pref_key_quick_app".equals(key)) {
            return 0;
        }
        if ("pref_key_cloud_game_icon".equals(key) || "pref_key_support_game_lottery".equals(key)
                || "pref_key_mini_game".equals(key) || "pref_key_mini_program_switch".equals(key)) {
            return 1;
        }
        return preference(key) == null ? -1 : 3;
    }

    public static boolean matchesSettingsSchema(List<String> keys, List<Integer> groups) {
        if (keys.size() != 16 || groups.size() != keys.size()) {
            return false;
        }
        Set<String> seen = new HashSet<>();
        for (int index = 0; index < keys.size(); index++) {
            String key = keys.get(index);
            if (!seen.add(key) || settingsGroup(key) < 0
                    || !Integer.valueOf(settingsGroup(key)).equals(groups.get(index))) {
                return false;
            }
        }
        return seen.containsAll(PREFERENCES.keySet()) && seen.contains(SECURITY_KEY);
    }

    public static Boolean preference(String key) {
        return PREFERENCES.get(key);
    }
}
