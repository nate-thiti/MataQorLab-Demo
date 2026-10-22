-- Enterprise is billed per organization: USD 99/month includes two seats,
-- then USD 39/month for each additional seat.
ALTER TABLE public.plans
    ADD COLUMN IF NOT EXISTS included_seats INTEGER NOT NULL DEFAULT 1;

ALTER TABLE public.plans
    ADD COLUMN IF NOT EXISTS additional_seat_price_monthly INTEGER NOT NULL DEFAULT 0;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'plans_included_seats_check'
          AND conrelid = 'public.plans'::regclass
    ) THEN
        ALTER TABLE public.plans
            ADD CONSTRAINT plans_included_seats_check
            CHECK (included_seats BETWEEN 1 AND 500);
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'plans_additional_seat_price_monthly_check'
          AND conrelid = 'public.plans'::regclass
    ) THEN
        ALTER TABLE public.plans
            ADD CONSTRAINT plans_additional_seat_price_monthly_check
            CHECK (additional_seat_price_monthly BETWEEN 0 AND 100000);
    END IF;
END;
$$;

UPDATE public.plans
SET
    description = 'Self-service team plan: USD 99 per organization includes 2 users, then USD 39 per additional user',
    price_monthly = 99,
    price_yearly = 1188,
    included_seats = 2,
    additional_seat_price_monthly = 39
WHERE lower(name) = 'enterprise';

COMMENT ON COLUMN public.plans.included_seats IS
    'Number of seats included in the recurring plan base price';
COMMENT ON COLUMN public.plans.additional_seat_price_monthly IS
    'USD charged per month for each seat above included_seats';
