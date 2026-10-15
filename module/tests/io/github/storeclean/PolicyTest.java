package io.github.storeclean;

import java.util.Map;

public final class PolicyTest {
    public static void main(String[] args) {
        int off = 0;
        int on = 0;
        for (Boolean value : Policy.PREFERENCES.values()) {
            if (value) {
                on++;
            } else {
                off++;
            }
        }
        require(off == 11 && on == 4, "all controlled menu options");
        require(Policy.preference(Policy.SECURITY_KEY) == null, "security exclusion");
        require(Policy.preference("unrelated") == null, "unknown key pass-through");
        require(Policy.preference(null) == null, "null key pass-through");
        require(Policy.GETTERS.size() == 15, "all getter candidates");
        require(Policy.GETTERS.get("needBlockWelfare"), "inverted welfare getter");
        require(!Policy.GETTERS.containsKey("isSupportAppSecurityCheck"), "security getter exclusion");
        require(Policy.supports("4.126.10", 40007640), "version 1");
        require(Policy.supports("4.126.s.1", 40007621), "version 2");
        require(Policy.supports("4.126.s.2", 40007622), "version 3");
        require(Policy.supports("4.127.11", 40007661), "new registered version");
        require(!Policy.supports("4.127.11", 40007640), "new version code mismatch");
        require(!Policy.allowsStructuralProbe("4.127.11", 40007640), "known mismatch is not a candidate");
        require(Policy.allowsStructuralProbe("4.128.12", 40007700), "future 4.x structural candidate");
        require(Policy.allowsStructuralProbe("4.128.s.1", 40007701), "future s branch candidate");
        require(!Policy.allowsStructuralProbe("5.1.1", 50000001), "other major rejected");
        require(!Policy.allowsStructuralProbe("4.128.12", 0), "invalid code rejected");
        require(!Policy.allowsStructuralProbe(null, 40007700), "null candidate rejected");
        java.util.List<String> keys = new java.util.ArrayList<>(Policy.PREFERENCES.keySet());
        keys.add(Policy.SECURITY_KEY);
        java.util.List<Integer> groups = new java.util.ArrayList<>();
        for (String key : keys) {
            groups.add(Policy.settingsGroup(key));
        }
        require(Policy.matchesSettingsSchema(keys, groups), "complete 16-key schema");
        groups.set(0, 3);
        require(!Policy.matchesSettingsSchema(keys, groups), "wrong category rejected");
        groups.set(0, Policy.settingsGroup(keys.get(0)));
        keys.set(0, "new_uncontrolled_option");
        require(!Policy.matchesSettingsSchema(keys, groups), "new setting rejected");
        keys.set(0, keys.get(1));
        require(!Policy.matchesSettingsSchema(keys, groups), "duplicate setting rejected");
        keys.remove(0);
        require(!Policy.matchesSettingsSchema(keys, groups), "missing setting rejected");
        require(!Policy.supports("4.126.s.2", 40007621), "mismatched name/code");
        require(!Policy.supports("future", 40007640), "unknown version");
        require(!Policy.supports(null, 0), "null version");
        Map<String, Boolean> before = new java.util.HashMap<>(Policy.PREFERENCES);
        Policy.preference("pref_key_short_play");
        require(before.equals(Policy.PREFERENCES), "reads do not mutate policy");
        try {
            Policy.PREFERENCES.put("unrelated", true);
            throw new AssertionError("mutable policy");
        } catch (UnsupportedOperationException expected) {
            // Expected immutable configuration.
        }
        System.out.println("PASS: 11 off, 4 on, exclusions, registered/candidate gates, complete schema checks, immutable policy");
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
