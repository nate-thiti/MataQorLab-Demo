import api from './api.js';

export const handleStripeCheckout = async ({
  user_id,
  plan_id,
  seats = 1,
  organization_name = null,
}) => {
  try {
    const response = await api.post('/api/v1/stripe/checkout-session', {
      user_id,
      plan_id,
      seats,
      organization_name
    });

    if (response.data?.url) {
      // ส่งผู้ใช้ไปยังหน้าชำระเงินของ Stripe (Sandbox Mode)
      window.location.href = response.data.url;
    } else {
      throw new Error("Stripe checkout session URL is missing.");
    }
  } catch (error) {
    console.error("Failed to initiate Stripe Checkout:", error);
    const msg =
      error.response?.data?.detail ||
      (typeof error.message === 'string' ? error.message : null) ||
      'เกิดข้อผิดพลาดในการเชื่อมต่อเพื่อชำระเงิน กรุณาลองใหม่อีกครั้ง';
    throw new Error(msg, { cause: error });
  }
};

export const handleCancelSubscription = async ({ user_id }) => {
  try {
    const response = await api.post('/api/v1/stripe/cancel-subscription', {
      user_id
    });
    return response.data;
  } catch (error) {
    console.error("Failed to cancel Stripe subscription:", error);
    const errMsg = error.response?.data?.detail || "เกิดข้อผิดพลาดในการยกเลิกการสมัครสมาชิก กรุณาลองใหม่อีกครั้ง";
    throw new Error(errMsg, { cause: error });
  }
};
