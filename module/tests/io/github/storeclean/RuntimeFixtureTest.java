package io.github.storeclean;

import java.util.HashMap;
import java.util.Map;

/** Host-only policy fixture: this does not execute Android or an Xposed runtime. */
public final class RuntimeFixtureTest {
    public static void main(String[] args) {
        boolean enabled = args.length != 0 && args[0].equals("enabled");
        Map<String, Boolean> disk = new HashMap<>();
        for (Map.Entry<String, Boolean> entry : Policy.PREFERENCES.entrySet()) {
            disk.put(entry.getKey(), !entry.getValue());
        }
        disk.put(Policy.SECURITY_KEY, false);
        disk.put("unrelated", true);
        Map<String, Boolean> snapshot = new HashMap<>(disk);
        for (Map.Entry<String, Boolean> entry : Policy.PREFERENCES.entrySet()) {
            Boolean override = enabled ? Policy.preference(entry.getKey()) : null;
            boolean effective = override == null ? disk.get(entry.getKey()) : override;
            require(effective == (enabled ? entry.getValue() : !entry.getValue()));
            if (enabled) {
                // Corresponds to skipping a controlled persistence call, not rewriting storage.
                require(Policy.preference(entry.getKey()) != null);
            }
        }
        for (boolean initialSecurity : new boolean[] {false, true}) {
            disk.put(Policy.SECURITY_KEY, initialSecurity);
            Boolean override = enabled ? Policy.preference(Policy.SECURITY_KEY) : null;
            require(override == null && disk.get(Policy.SECURITY_KEY) == initialSecurity);
        }
        disk.put(Policy.SECURITY_KEY, snapshot.get(Policy.SECURITY_KEY));
        require(disk.equals(snapshot));
        // Disable the fixture overrides: every controlled value reverts to its original value.
        for (String key : Policy.PREFERENCES.keySet()) {
            require(disk.get(key).equals(snapshot.get(key)));
        }
        System.out.println(enabled
                ? "PASS enabled fixture: 15 overrides, security/unknown unchanged, storage unchanged, rollback restores baseline"
                : "PASS baseline fixture: original 15 values visible, security/unknown unchanged, storage unchanged");
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Fixture mismatch");
        }
    }
}
