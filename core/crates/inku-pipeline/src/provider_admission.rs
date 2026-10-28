//! Provider budgets. The host owns the clock, persistence and waiting.
use jiff::{Timestamp, tz::TimeZone};
use serde_json::{Value, json};
use std::sync::OnceLock;
use std::time::UNIX_EPOCH;

const WINDOW: f64 = 62.0;
const TZIF: &[u8] = include_bytes!("../data/los_angeles.tzif");

fn day(now: f64, kind: &str) -> Result<String, &'static str> {
    if !now.is_finite() || now < i64::MIN as f64 || now >= i64::MAX as f64 {
        return Err("corrupt_state");
    }
    let timestamp = Timestamp::from_second(now.floor() as i64).map_err(|_| "corrupt_state")?;
    let tz = if kind == "gemini" {
        static LA: OnceLock<TimeZone> = OnceLock::new();
        LA.get_or_init(|| TimeZone::tzif("America/Los_Angeles", TZIF).expect("embedded timezone"))
            .clone()
    } else {
        TimeZone::UTC
    };
    Ok(timestamp.to_zoned(tz).date().to_string())
}
fn num(value: &Value) -> Result<f64, &'static str> {
    value
        .as_f64()
        .filter(|x| x.is_finite())
        .ok_or("corrupt_state")
}
fn uint(value: &Value) -> Result<u64, &'static str> {
    value.as_u64().ok_or("corrupt_state")
}
fn limit(value: &Value) -> Result<u64, &'static str> {
    let n = uint(value)?;
    Ok(if n == 0 {
        0
    } else {
        (n / 10 * 9 + n % 10 * 9 / 10).max(1)
    })
}
fn json_body(request: &Value) -> Option<Value> {
    let bytes: Vec<u8> = if request["raw_bytes"].is_array() {
        serde_json::from_value(request["raw_bytes"].clone()).ok()?
    } else {
        request["raw"].as_str().unwrap_or("").as_bytes().to_vec()
    };
    if let Ok(value) = serde_json::from_slice(&bytes) {
        return Some(value);
    }
    let bytes = bytes.strip_prefix(&[0xef, 0xbb, 0xbf]).unwrap_or(&bytes);
    if let Ok(value) = serde_json::from_slice(bytes) {
        return Some(value);
    }
    let (width, little, offset) = if bytes.starts_with(&[0xff, 0xfe, 0, 0]) {
        (4, true, 4)
    } else if bytes.starts_with(&[0, 0, 0xfe, 0xff]) {
        (4, false, 4)
    } else if bytes.starts_with(&[0xff, 0xfe]) {
        (2, true, 2)
    } else if bytes.starts_with(&[0xfe, 0xff]) {
        (2, false, 2)
    } else if bytes.starts_with(&[0, 0, 0]) {
        (4, false, 0)
    } else if bytes.len() >= 4 && bytes[1..4] == [0, 0, 0] {
        (4, true, 0)
    } else if bytes.first() == Some(&0) {
        (2, false, 0)
    } else if bytes.get(1) == Some(&0) {
        (2, true, 0)
    } else {
        return None;
    };
    let input = &bytes[offset..];
    if !input.len().is_multiple_of(width) {
        return None;
    }
    let decoded = if width == 2 {
        let words: Vec<u16> = input
            .as_chunks::<2>()
            .0
            .iter()
            .map(|v| {
                if little {
                    u16::from_le_bytes([v[0], v[1]])
                } else {
                    u16::from_be_bytes([v[0], v[1]])
                }
            })
            .collect();
        String::from_utf16(&words).ok()?
    } else {
        input
            .as_chunks::<4>()
            .0
            .iter()
            .map(|v| {
                let b = [v[0], v[1], v[2], v[3]];
                char::from_u32(if little {
                    u32::from_le_bytes(b)
                } else {
                    u32::from_be_bytes(b)
                })
            })
            .collect::<Option<String>>()?
    };
    serde_json::from_str(&decoded).ok()
}

fn retry(request: &Value) -> f64 {
    let now = request["now"].as_f64().unwrap_or(0.0);
    let mut wait = WINDOW;
    if let Some(header) = request["retry_after"].as_str().filter(|s| !s.is_empty()) {
        let seconds = header.trim().parse::<f64>().ok().or_else(|| {
            httpdate::parse_http_date(header)
                .ok()
                .map(|t| match t.duration_since(UNIX_EPOCH) {
                    Ok(d) => d.as_secs_f64() - now,
                    Err(e) => -e.duration().as_secs_f64() - now,
                })
                .or_else(|| {
                    jiff::fmt::strtime::parse("%a, %d %b %Y %H:%M:%S %z", header)
                        .ok()
                        .and_then(|value| value.to_timestamp().ok())
                        .map(|value| value.as_second() as f64 - now)
                })
        });
        if let Some(s) = seconds.filter(|s| s.is_finite()) {
            wait = wait.max(s);
        }
    }
    if let Some(body) = json_body(request)
        && let Some(details) = body["error"]["details"].as_array()
    {
        for detail in details {
            if detail["@type"] == "type.googleapis.com/google.rpc.RetryInfo"
                && let Some(delay) = detail["retryDelay"]
                    .as_str()
                    .and_then(|s| s.strip_suffix('s'))
            {
                match delay.trim().parse::<f64>() {
                    Ok(s) if s.is_finite() => wait = wait.max(s),
                    Ok(_) => (),
                    Err(_) => break,
                }
            }
        }
    }
    wait
}
fn process(r: &Value) -> Result<Value, &'static str> {
    let action = r["action"].as_str().ok_or("invalid_request")?;
    if action == "retry" {
        return Ok(json!({"seconds": retry(r)}));
    }
    if action == "preflight" {
        let tpm = limit(&r["limits"]["tpm"])?;
        let input = uint(&r["input_tokens"])?;
        return Ok(if tpm != 0 && input > tpm {
            json!({"decision":"reject", "reason":"request exceeds the configured input-token budget"})
        } else {
            json!({"decision":"continue"})
        });
    }
    if action == "limits" {
        return Ok(json!({"rpm":limit(&r["limits"]["rpm"])?, "tpm":limit(&r["limits"]["tpm"])?}));
    }
    let now = num(&r["now"])?;
    if action == "day" {
        return Ok(json!({"day":day(now, r["kind"].as_str().unwrap_or(""))?}));
    }
    let mut state = r["state"].clone();
    if !state.is_object() || !state["events"].is_array() {
        return Err("corrupt_state");
    }
    if action == "settle" || action == "pause" {
        let not_before = num(&state["not_before"])?;
        if action == "pause" || r["input_tokens"].is_null() {
            let seconds = if action == "pause" {
                num(&r["seconds"])?
            } else {
                WINDOW
            };
            let until = now + seconds;
            if !until.is_finite() {
                return Err("corrupt_state");
            }
            if until > not_before {
                state["not_before"] = json!(until);
            }
        } else {
            let tokens = uint(&r["input_tokens"])?;
            for event in state["events"].as_array_mut().ok_or("corrupt_state")? {
                if event["id"] == r["id"] {
                    event["tokens"] = json!(tokens);
                }
            }
        }
        return Ok(json!({"state":state}));
    }
    if action != "admit" {
        return Err("invalid_request");
    }
    let rpm = limit(&r["limits"]["rpm"])?;
    let tpm = limit(&r["limits"]["tpm"])?;
    let rpd = uint(&r["limits"]["rpd"])?;
    let input = uint(&r["input_tokens"])?;
    if tpm != 0 && input > tpm {
        return Ok(
            json!({"decision":"reject", "reason":"request exceeds the configured input-token budget"}),
        );
    }
    let current_day = day(now, r["kind"].as_str().unwrap_or(""))?;
    let mut events = Vec::new();
    for event in state["events"].as_array().ok_or("corrupt_state")? {
        let at = num(&event["at"])?;
        uint(&event["tokens"])?;
        if event["id"].as_str().is_none() {
            return Err("corrupt_state");
        }
        if at + WINDOW > now {
            events.push(event.clone());
        }
    }
    state["events"] = json!(events);
    if state["day"].as_str().ok_or("corrupt_state")? != current_day {
        state["day"] = json!(current_day);
        state["daily"] = json!(0);
    }
    let daily = uint(&state["daily"])?;
    if rpd != 0 && daily >= rpd {
        return Ok(
            json!({"decision":"reject", "reason":"provider daily request budget exhausted"}),
        );
    }
    let mut delay = (num(&state["not_before"])? - now).max(0.0);
    let events = state["events"].as_array().ok_or("corrupt_state")?;
    let mut total = input;
    for event in events {
        total = total
            .checked_add(uint(&event["tokens"])?)
            .ok_or("corrupt_state")?;
    }
    if (rpm != 0 && events.len() as u64 >= rpm) || (tpm != 0 && total > tpm) {
        let oldest = events
            .iter()
            .map(|event| num(&event["at"]))
            .collect::<Result<Vec<_>, _>>()?
            .into_iter()
            .reduce(f64::min)
            .ok_or("corrupt_state")?;
        delay = delay.max(oldest + WINDOW - now);
    }
    if delay > 0.0 {
        return Ok(json!({"decision":"wait", "seconds":delay, "state":state}));
    }
    let daily = daily.checked_add(1).ok_or("corrupt_state")?;
    let id = r["id"].as_str().ok_or("invalid_request")?;
    state["events"]
        .as_array_mut()
        .ok_or("corrupt_state")?
        .push(json!({"id":id,"at":r["now"],"tokens":input}));
    state["daily"] = json!(daily);
    Ok(json!({"decision":"admit", "state":state}))
}

pub fn provider_admission_json(input: &[u8]) -> Vec<u8> {
    let result = serde_json::from_slice::<Value>(input)
        .map_err(|_| "invalid_request")
        .and_then(|r| process(&r));
    serde_json::to_vec(&match result {
        Ok(v) => v,
        Err(e) => json!({"error":e}),
    })
    .expect("JSON response")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn matches_original_server_cases() {
        let fixture: Value = serde_json::from_str(include_str!(
            "../../../../server/tests/data/provider-admission-cases.json"
        ))
        .unwrap();
        for case in fixture["cases"].as_array().unwrap() {
            let actual: Value = serde_json::from_slice(&provider_admission_json(
                &serde_json::to_vec(&case["request"]).unwrap(),
            ))
            .unwrap();
            assert_eq!(actual, case["expected"], "{}", case["name"]);
        }
    }
    #[test]
    fn effective_limits_need_no_clock_and_do_not_overflow() {
        let request = json!({"action":"limits","limits":{"rpm":1,"tpm":u64::MAX}});
        let actual: Value = serde_json::from_slice(&provider_admission_json(
            &serde_json::to_vec(&request).unwrap(),
        ))
        .unwrap();
        assert_eq!(actual, json!({"rpm":1,"tpm":16602069666338596453_u64}));
    }
    #[test]
    fn retry_after_accepts_numeric_timezone() {
        let request = json!({"action":"retry","now":0,"retry_after":"Thu, 01 Jan 1970 00:02:00 +0000","raw":""});
        let actual: Value = serde_json::from_slice(&provider_admission_json(
            &serde_json::to_vec(&request).unwrap(),
        ))
        .unwrap();
        assert_eq!(actual["seconds"], 120.0);
    }
}
