package app.inku.mobile.llm

import java.io.ByteArrayOutputStream
import java.io.Closeable
import java.io.IOException
import java.math.BigInteger
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketTimeoutException
import java.security.AlgorithmParameters
import java.security.KeyFactory
import java.security.SecureRandom
import java.security.Signature
import java.security.spec.ECGenParameterSpec
import java.security.spec.ECParameterSpec
import java.security.spec.ECPoint
import java.security.spec.ECPublicKeySpec
import java.security.spec.RSAPublicKeySpec
import java.util.Base64
import org.json.JSONObject

/*
 * The host's part of the shared core's sign-in procedures (`chatgpt_flow_start`,
 * `chatgpt_flow_next`, step 5): the core answers what to do next, and these do
 * what only Android can do — the store's shape, the loopback socket, the
 * signature check with JCA, randomness and the local offset. The plan manager
 * runs the procedure and holds the locks.
 */

/**
 * The store as the core reads it: finished registrations (with `sub`) under
 * `profiles` in seconds, unfinished ones under `registrations_pending`.
 * Before step 5 Android kept an unfinished registration among the profiles;
 * it moves on the next write.
 */
internal fun coreStore(value: JSONObject): JSONObject {
    val result = JSONObject(value.toString())
    val profiles = value.optJSONObject("profiles") ?: JSONObject()
    val finished = JSONObject()
    val pending = value.optJSONObject("registrations_pending")?.let { JSONObject(it.toString()) } ?: JSONObject()
    profiles.keys().forEach { id ->
        val profile = profiles.getJSONObject(id)
        if (profile.has("sub")) finished.put(id, ChatGptCore.toCore(profile))
        else pending.put(id, JSONObject().put("client_id", profile.opt("client_id") ?: JSONObject.NULL))
    }
    return result.put("profiles", finished).put("registrations_pending", pending)
}

/** The core's store as Android keeps it: the same shape, in milliseconds. */
internal fun hostStore(value: JSONObject): JSONObject {
    val result = JSONObject(value.toString())
    val profiles = value.optJSONObject("profiles") ?: JSONObject()
    result.put("profiles", JSONObject().apply { profiles.keys().forEach { put(it, ChatGptCore.fromCore(profiles.getJSONObject(it))) } })
    if (result.isNull("active")) result.remove("active")
    return result
}

/** `random`: each name's bytes, base64url without padding. */
internal fun chatGptRandom(sizes: JSONObject): JSONObject {
    val random = SecureRandom()
    val values = JSONObject()
    sizes.keys().forEach { name -> values.put(name, base64Url(ByteArray(sizes.getInt(name)).also(random::nextBytes))) }
    return JSONObject().put("values", values)
}

/** `offset`: this device's offset from UTC at that local date or time, in seconds. */
internal fun localOffsetSeconds(local: String): Any = runCatching {
    val time = runCatching { java.time.LocalDateTime.parse(local) }.getOrElse { java.time.LocalDate.parse(local).atStartOfDay() }
    java.time.ZoneId.systemDefault().rules.getOffset(time).totalSeconds
}.getOrNull() ?: JSONObject.NULL

/** `verify`: JCA checks an advertised RSA or P-256 signature; the key's shape is checked here first. */
internal fun verifyChatGptSignature(algorithm: String, key: JSONObject, signingInput: String, signature: String): Boolean = runCatching {
    val decoder = Base64.getUrlDecoder()
    val publicKey = when (algorithm) {
        "RS256" -> {
            require(key.getString("kty") == "RSA")
            val n = BigInteger(1, decoder.decode(key.getString("n")))
            val e = BigInteger(1, decoder.decode(key.getString("e")))
            require(n.bitLength() in 2048..8192 && e >= BigInteger.valueOf(3) && e.bitLength() <= 32)
            KeyFactory.getInstance("RSA").generatePublic(RSAPublicKeySpec(n, e))
        }
        "ES256" -> {
            require(key.getString("kty") == "EC" && key.getString("crv") == "P-256")
            val parameters = AlgorithmParameters.getInstance("EC").apply { init(ECGenParameterSpec("secp256r1")) }
                .getParameterSpec(ECParameterSpec::class.java)
            val x = decoder.decode(key.getString("x")); val y = decoder.decode(key.getString("y"))
            require(x.size == 32 && y.size == 32)
            KeyFactory.getInstance("EC").generatePublic(ECPublicKeySpec(ECPoint(BigInteger(1, x), BigInteger(1, y)), parameters))
        }
        else -> error("unsupported algorithm")
    }
    val verifier = Signature.getInstance(if (algorithm == "RS256") "SHA256withRSA" else "SHA256withECDSA")
    verifier.initVerify(publicKey)
    verifier.update(signingInput.toByteArray(Charsets.US_ASCII))
    val raw = decoder.decode(signature)
    verifier.verify(if (algorithm == "ES256") ecdsaDer(raw) else raw)
}.getOrDefault(false)

private fun ecdsaDer(raw: ByteArray): ByteArray {
    require(raw.size == 64)
    fun integer(bytes: ByteArray): ByteArray {
        val first = bytes.indexOfFirst { it != 0.toByte() }.let { if (it < 0) bytes.lastIndex else it }
        val value = bytes.copyOfRange(first, bytes.size)
        return if (value[0].toInt() and 128 != 0) byteArrayOf(0) + value else value
    }
    val r = integer(raw.copyOfRange(0, 32)); val s = integer(raw.copyOfRange(32, 64))
    return byteArrayOf(0x30, (r.size + s.size + 4).toByte(), 0x02, r.size.toByte()) + r + byteArrayOf(0x02, s.size.toByte()) + s
}

/**
 * The loopback listener a sign-in returns to (`listen`, `await_callback`,
 * `respond`). The core reads the request's head and writes the page; this
 * only accepts, hands the head over, and answers what the core says.
 */
internal class ChatGptCallbackServer : Closeable {
    private val listener = ServerSocket(0, 4, InetAddress.getByName("127.0.0.1"))
    private var connection: Socket? = null
    val port: Int get() = listener.localPort

    /** The next connection's request head, before its blank line (at most 16 KiB); null once [deadline] passed. */
    fun await(deadline: Long, now: () -> Long, cancelled: () -> Boolean): ByteArray? {
        listener.soTimeout = 1000
        while (true) {
            if (cancelled()) throw ChatGptException("chatgpt_cancelled")
            if (now() >= deadline) return null
            val socket = try { listener.accept() } catch (_: SocketTimeoutException) { continue }
            catch (error: IOException) { if (cancelled()) throw ChatGptException("chatgpt_cancelled"); throw error }
            connection?.close()
            connection = socket
            socket.soTimeout = 1000
            return readHead(socket)
        }
    }

    private fun readHead(socket: Socket): ByteArray {
        val input = socket.getInputStream()
        val head = ByteArrayOutputStream()
        try {
            while (head.size() < HEAD_LIMIT + 4) {
                val value = input.read()
                if (value == -1) break
                head.write(value)
                val bytes = head.size()
                if (bytes >= 4) {
                    val all = head.toByteArray()
                    if (all[bytes - 4] == '\r'.code.toByte() && all[bytes - 3] == '\n'.code.toByte() &&
                        all[bytes - 2] == '\r'.code.toByte() && all[bytes - 1] == '\n'.code.toByte()) {
                        return all.copyOf(bytes - 4)
                    }
                }
            }
        } catch (_: IOException) { /* What arrived is read by the core, which refuses a head cut short. */ }
        return head.toByteArray()
    }

    /** Writes the core's answer to the connection the head came on, and closes it. */
    fun respond(status: Int, headers: JSONObject, body: String) {
        val socket = connection ?: return
        connection = null
        socket.use {
            runCatching {
                val bytes = body.toByteArray(Charsets.UTF_8)
                val head = StringBuilder("HTTP/1.1 $status ${if (status == 200) "OK" else "Bad Request"}\r\n")
                headers.keys().forEach { name -> head.append(name).append(": ").append(headers.getString(name)).append("\r\n") }
                head.append("Content-Length: ").append(bytes.size).append("\r\n\r\n")
                it.getOutputStream().apply { write(head.toString().toByteArray(Charsets.US_ASCII)); write(bytes); flush() }
            }
        }
    }

    override fun close() {
        runCatching { connection?.close() }
        connection = null
        runCatching { listener.close() }
    }

    private companion object {
        const val HEAD_LIMIT = 16 * 1024
    }
}
