import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import {
  DEFAULT_LOCALE,
  LOCALE_COOKIE,
  SUPPORTED_LOCALES,
} from "./src/utils/locale.js";
import {
  isInvalidRefreshTokenError,
  isSupabaseAuthCookie,
} from "./src/utils/supabaseAuthError.js";

type CookieToSet = {
  name: string;
  value: string;
  options: CookieOptions;
};

function getSupabaseEnv() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return null;
  return { url, key };
}

function expireSupabaseAuthCookies(request: NextRequest, response: NextResponse) {
  request.cookies.getAll().forEach(({ name }) => {
    if (isSupabaseAuthCookie(name)) {
      response.cookies.set(name, "", { path: "/", maxAge: 0 });
    }
  });
  return response;
}

function buildForwardedHeaders(request: NextRequest, locale: string) {
  const headers = new Headers(request.headers);
  headers.set("x-mataqor-locale", locale);
  return headers;
}

function persistLocale(response: NextResponse, locale: string) {
  response.headers.set("Content-Language", locale);
  response.cookies.set(LOCALE_COOKIE, locale, {
    path: "/",
    maxAge: 60 * 60 * 24 * 365,
    sameSite: "lax",
  });
  return response;
}

async function updateSupabaseSession(request: NextRequest, locale: string) {
  const forwardedHeaders = buildForwardedHeaders(request, locale);
  const nextResponse = () => NextResponse.next({
    request: { headers: forwardedHeaders },
  });
  const env = getSupabaseEnv();
  if (!env) {
    const response = nextResponse();
    response.headers.set("Cache-Control", "private, no-store");
    return persistLocale(response, locale);
  }

  let response = nextResponse();

  const supabase = createServerClient(env.url, env.key, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet: CookieToSet[]) {
        cookiesToSet.forEach(({ name, value }) => {
          request.cookies.set(name, value);
        });
        response = nextResponse();
        cookiesToSet.forEach(({ name, value, options }) => {
          response.cookies.set(name, value, options);
        });
      },
    },
  });

  try {
    const { error } = await supabase.auth.getUser();
    if (isInvalidRefreshTokenError(error)) {
      response = expireSupabaseAuthCookies(request, response);
    }
  } catch (error) {
    if (isInvalidRefreshTokenError(error)) {
      response = expireSupabaseAuthCookies(request, response);
    } else {
      // A transient DNS/network outage to Supabase must not turn every Next.js
      // route into a failed render. Client-side auth and protected backend APIs
      // still enforce the session; the next request will refresh it again.
      console.warn("Supabase session refresh temporarily unavailable", error);
    }
  }

  response.headers.set("Cache-Control", "private, no-store");
  return persistLocale(response, locale);
}

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const pathLocale = SUPPORTED_LOCALES.find(
    (locale) => pathname.startsWith(`/${locale}/`) || pathname === `/${locale}`,
  );

  if (!pathLocale) {
    const country = request.headers.get("x-vercel-ip-country") || "TH";
    const acceptLanguage = request.headers.get("accept-language");
    const savedLocale = request.cookies.get(LOCALE_COOKIE)?.value;

    let detectedLocale = DEFAULT_LOCALE;

    if (SUPPORTED_LOCALES.includes(savedLocale as (typeof SUPPORTED_LOCALES)[number])) {
      detectedLocale = savedLocale as (typeof SUPPORTED_LOCALES)[number];
    } else if (country !== "TH") {
      detectedLocale = "en";
    } else if (acceptLanguage && !acceptLanguage.includes("th")) {
      detectedLocale = "en";
    }

    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = `/${detectedLocale}${pathname}`;
    return NextResponse.redirect(redirectUrl);
  }

  return updateSupabaseSession(request, pathLocale);
}

export const config = {
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|.*\\.png$).*)",
  ],
};
