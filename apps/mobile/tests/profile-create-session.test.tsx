import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import type { BuiltProfileFields } from "../src/features/profile/model";

const mocks = vi.hoisted(() => ({ create: vi.fn(), replace: vi.fn() }));
let submit: (fields: BuiltProfileFields) => Promise<void>;
vi.mock("expo-router", () => ({
  useRouter: () => ({ replace: mocks.replace, back: vi.fn() }),
}));
vi.mock("react-native-safe-area-context", () => ({
  SafeAreaView: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));
vi.mock("../src/features/profile/components/ProfileForm", () => ({
  ProfileForm: (props: { onSubmit: typeof submit }) => {
    submit = props.onSubmit;
    return null;
  },
}));
vi.mock("../src/features/profile/api", () => ({
  profileApi: { createProfileItem: mocks.create },
  ProfileUserError: class extends Error {},
}));

import ProfileCreateScreen from "../src/features/profile/screens/ProfileCreateScreen";
import { sessionStore } from "../src/auth/sessionStore";
import { activeProfileCreateRecovery as recovery } from "../src/features/profile/createRecovery";
import {
  buildProfileFields,
  EMPTY_PROFILE_DRAFT,
} from "../src/features/profile/model";

afterEach(() => {
  recovery.resolve();
  mocks.create.mockReset();
  mocks.replace.mockClear();
  sessionStore.setSignedOut();
});

it.each(["success", "failure"])(
  "ignores a late account-A %s without clearing account-B recovery",
  async (outcome) => {
    const built = buildProfileFields({
      ...EMPTY_PROFILE_DRAFT,
      key: "preferred_name",
      label: "Name",
    });
    if (!built.ok) throw new Error(built.error);
    let resolve!: (value: { id: string }) => void;
    let reject!: (error: Error) => void;
    mocks.create.mockReturnValueOnce(
      new Promise((yes, no) => {
        resolve = yes;
        reject = no;
      }),
    );
    sessionStore.setSignedIn("account-a", null);
    renderToStaticMarkup(<ProfileCreateScreen />);
    const pendingA = submit(built.fields);
    sessionStore.setSignedIn("account-b", null);
    recovery.resolve(); // App session-change handler clears the old attempt.
    renderToStaticMarkup(<ProfileCreateScreen />);
    mocks.create.mockRejectedValueOnce(new TypeError("response lost"));
    await expect(submit(built.fields)).rejects.toThrow("uncertain");
    const attemptB = recovery.retryOriginal();
    expect(attemptB).not.toBeNull();
    if (outcome === "success") resolve({ id: "account-a-item" });
    else reject(new TypeError("late failure"));
    await pendingA;
    expect(recovery.retryOriginal()).toBe(attemptB);
    expect(mocks.replace).not.toHaveBeenCalled();
  },
);
