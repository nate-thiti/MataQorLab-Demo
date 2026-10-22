export const E2E_MOCK_USER = {
  id: "e2e-user-id",
  email: "e2e@test.com",
};

export function getE2eMockUser() {
  if (typeof document === "undefined") return null;
  if (!document.cookie.includes("e2e-authenticated=1")) return null;
  return E2E_MOCK_USER;
}
