import { getServerSession } from "next-auth";
import { NextResponse } from "next/server";
import { SignJWT } from "jose";
import { authOptions } from "../../../lib/auth";

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const secret = new TextEncoder().encode(process.env.NEXTAUTH_SECRET!);
  const token = await new SignJWT({ sub: session.user.email })
    .setProtectedHeader({ alg: "HS256" })
    .setExpirationTime("30d")
    .sign(secret);
  return NextResponse.json({ token });
}
