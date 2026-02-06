import { handlers } from "@/lib/auth"
import { NextRequest } from "next/server"

const { GET: AuthGET, POST: AuthPOST } = handlers

export async function GET(req: NextRequest) {
    const url = req.nextUrl.clone()
    if (!url.pathname.startsWith("/portal")) {
        url.pathname = `/portal${url.pathname}`
        const newReq = new NextRequest(url, req)
        return AuthGET(newReq)
    }
    return AuthGET(req)
}

export async function POST(req: NextRequest) {
    const url = req.nextUrl.clone()
    if (!url.pathname.startsWith("/portal")) {
        url.pathname = `/portal${url.pathname}`
        const newReq = new NextRequest(url, req)
        return AuthPOST(newReq)
    }
    return AuthPOST(req)
}
