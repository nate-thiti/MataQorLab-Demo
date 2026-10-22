const DEFAULT_INCLUDED_SEATS = 2;
const DEFAULT_ADDITIONAL_SEAT_PRICE_MONTHLY = 39;
const MIN_ENTERPRISE_SEATS = 2;
const MAX_ENTERPRISE_SEATS = 500;

function boundedInteger(value, fallback, minimum, maximum) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(maximum, Math.max(minimum, Math.trunc(parsed)));
}

export function calculateEnterpriseMonthlyPrice(plan, seats) {
  const includedSeats = boundedInteger(
    plan?.included_seats,
    DEFAULT_INCLUDED_SEATS,
    MIN_ENTERPRISE_SEATS,
    MAX_ENTERPRISE_SEATS,
  );
  const additionalSeatPrice = boundedInteger(
    plan?.additional_seat_price_monthly,
    DEFAULT_ADDITIONAL_SEAT_PRICE_MONTHLY,
    0,
    100000,
  );
  const seatCount = boundedInteger(
    seats,
    MIN_ENTERPRISE_SEATS,
    MIN_ENTERPRISE_SEATS,
    MAX_ENTERPRISE_SEATS,
  );
  const basePrice = Math.max(0, Number(plan?.price_monthly) || 0);
  const additionalSeats = Math.max(0, seatCount - includedSeats);

  return {
    additionalSeatPrice,
    additionalSeats,
    basePrice,
    includedSeats,
    monthlyTotal: basePrice + (additionalSeats * additionalSeatPrice),
    seatCount,
  };
}
