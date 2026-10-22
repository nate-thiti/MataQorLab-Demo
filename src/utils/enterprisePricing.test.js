import { describe, expect, it } from 'vitest';

import { calculateEnterpriseMonthlyPrice } from './enterprisePricing.js';

const plan = {
  price_monthly: 99,
  included_seats: 2,
  additional_seat_price_monthly: 39,
};

describe('calculateEnterpriseMonthlyPrice', () => {
  it('includes the first two seats in the organization base price', () => {
    expect(calculateEnterpriseMonthlyPrice(plan, 2)).toMatchObject({
      additionalSeats: 0,
      monthlyTotal: 99,
      seatCount: 2,
    });
  });

  it('charges only seats above the included quantity', () => {
    expect(calculateEnterpriseMonthlyPrice(plan, 5)).toMatchObject({
      additionalSeats: 3,
      monthlyTotal: 216,
      seatCount: 5,
    });
  });

  it('uses safe display defaults before the pricing migration is available', () => {
    expect(calculateEnterpriseMonthlyPrice({ price_monthly: 99 }, 3)).toMatchObject({
      additionalSeatPrice: 39,
      includedSeats: 2,
      monthlyTotal: 138,
    });
  });
});
