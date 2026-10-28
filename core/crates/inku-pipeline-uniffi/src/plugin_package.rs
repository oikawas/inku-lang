//! Host-neutral plugin-package inspection and example-drawing handshake.
use crate::{plugin_picture, zip_reader};
use base64::{Engine, engine::general_purpose::STANDARD};
use regex::Regex;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

const MAX_PACKAGE: usize = 1_000_000;
const MAX_PICTURE: usize = 2 * 1024 * 1024;
const MAX_ARCHIVE: usize = 16 * 1024 * 1024;
const MAX_PICTURES: usize = 64 * 1024 * 1024;

fn problem(path: &str, code: &str, detail: impl ToString) -> Value {
    json!({"path":path,"code":code,"detail":detail.to_string()})
}
fn refused(problems: Vec<Value>) -> Value {
    json!({"outcome":"refused","problems":problems})
}
fn s(v: &Value) -> &str {
    v.as_str().unwrap_or("")
}
fn python_string_field(object: &Value, key: &str) -> String {
    match object.get(key) {
        None => String::new(),
        Some(Value::Null) => "None".to_owned(),
        Some(Value::Bool(value)) => if *value { "True" } else { "False" }.to_owned(),
        Some(Value::String(value)) => value.clone(),
        Some(value) => value.to_string(),
    }
}
fn text(v: &Value, path: &str, problems: &mut Vec<Value>, limit: usize) -> String {
    if v.is_null() {
        return String::new();
    }
    let Some(value) = v.as_str() else {
        problems.push(problem(path, "not_a_string", ""));
        return String::new();
    };
    if value.chars().count() > limit {
        problems.push(problem(path, "text_too_long", limit));
        return String::new();
    }
    value.trim().to_owned()
}
type ArchivePictures = BTreeMap<String, Option<Vec<u8>>>;

fn archive(data: &[u8]) -> Result<(String, ArchivePictures), Vec<Value>> {
    let err = |code, detail: String| vec![problem("", code, detail)];
    if data.len() > MAX_ARCHIVE {
        return Err(err("archive_too_large", MAX_ARCHIVE.to_string()));
    }
    let convert = |e| match e {
        zip_reader::ZipError::TooManyMembers => err("too_many_archive_members", "256".into()),
        zip_reader::ZipError::Invalid(name) => err("invalid_zip", name),
    };
    let members = zip_reader::members(data).map_err(convert)?;
    let package = members
        .iter()
        .find(|m| m.name == "package.json")
        .ok_or_else(|| err("archive_without_package_json", "package.json".into()))?;
    let content = zip_reader::read(data, package, MAX_PACKAGE)
        .map_err(convert)?
        .ok_or_else(|| err("package_too_large", MAX_PACKAGE.to_string()))?;
    let doc = String::from_utf8(content).map_err(|_| err("not_utf8", "package.json".into()))?;
    let mut pictures = BTreeMap::new();
    let mut total = 0;
    for member in members
        .iter()
        .filter(|m| !m.name.ends_with('/') && m.name.to_lowercase().ends_with(".png"))
    {
        let content = zip_reader::read(data, member, MAX_PICTURE).map_err(convert)?;
        total += content.as_ref().map_or(0, Vec::len);
        if total > MAX_PICTURES {
            return Err(err("archive_too_large", MAX_PICTURES.to_string()));
        }
        pictures.insert(member.name.clone(), content);
    }
    Ok((doc, pictures))
}

fn parse(
    document: &str,
    pictures: Option<&BTreeMap<String, Option<Vec<u8>>>>,
    stored: bool,
) -> Result<Value, Vec<Value>> {
    if document.len() > MAX_PACKAGE {
        return Err(vec![problem("", "package_too_large", MAX_PACKAGE)]);
    }
    let raw: Value = serde_json::from_str(document).map_err(|e| {
        let message = e.to_string();
        let message = message
            .rsplit_once(" at line ")
            .map_or(message.as_str(), |(s, _)| s);
        vec![problem(
            "",
            "invalid_json",
            format!("{} (line {}, column {})", message, e.line(), e.column()),
        )]
    })?;
    let obj = raw
        .as_object()
        .ok_or_else(|| vec![problem("", "not_an_object", "")])?;
    let mut problems = Vec::new();
    let mut blocking = Vec::new();
    let package_keys = [
        "schema",
        "namespace",
        "name",
        "version",
        "description_ja",
        "description_en",
        "authors",
        "license",
        "words",
    ];
    let mut unknown: Vec<_> = obj
        .keys()
        .filter(|key| !package_keys.contains(&key.as_str()))
        .collect();
    unknown.sort();
    for key in unknown {
        problems.push(problem(key, "unknown_field", ""));
    }
    if s(&raw["schema"]) != "inku.plugin-package.v1" {
        problems.push(problem("schema", "wrong_schema", "inku.plugin-package.v1"));
    }
    let ident = Regex::new(r"^[A-Za-z][A-Za-z0-9_-]*$").unwrap();
    let mut namespace = s(&raw["namespace"]);
    let mut name = s(&raw["name"]);
    if !ident.is_match(namespace) {
        blocking.push(problem("namespace", "invalid_identifier", ""));
        namespace = "";
    }
    if !ident.is_match(name) {
        blocking.push(problem("name", "invalid_identifier", ""));
        name = "";
    }
    let version = s(&raw["version"]);
    let version_re = Regex::new(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$").unwrap();
    let version = if version_re.is_match(version) {
        version
    } else {
        problems.push(problem("version", "invalid_semantic_version", ""));
        ""
    };
    let desc_ja = text(
        &raw["description_ja"],
        "description_ja",
        &mut problems,
        2000,
    );
    let desc_en = text(
        &raw["description_en"],
        "description_en",
        &mut problems,
        2000,
    );
    let authors = match &raw["authors"] {
        Value::Null | Value::Bool(false) => vec![],
        Value::String(value) if value.is_empty() => vec![],
        Value::Number(value) if value.as_f64() == Some(0.0) => vec![],
        Value::Object(value) if value.is_empty() => vec![],
        Value::Array(a) if a.iter().all(Value::is_string) => a.clone(),
        _ => {
            problems.push(problem("authors", "not_a_list_of_strings", ""));
            vec![]
        }
    };
    let license = text(&raw["license"], "license", &mut problems, 200);
    let mut words = Vec::new();
    match raw["words"].as_array() {
        None => blocking.push(problem("words", "no_words", "")),
        Some(items) if items.is_empty() => blocking.push(problem("words", "no_words", "")),
        Some(items) if items.len() > 64 => blocking.push(problem("words", "too_many_words", 64)),
        Some(items) => {
            for (index, item) in items.iter().enumerate() {
                let path = format!("words[{index}]");
                let Some(item_obj) = item.as_object() else {
                    problems.push(problem(&path, "not_an_object", ""));
                    continue;
                };
                if !item["definition"].is_object() {
                    problems.push(problem(&format!("{path}.definition"), "not_an_object", ""));
                    continue;
                }
                let mut wp = Vec::new();
                let keys = [
                    "definition",
                    "summary_ja",
                    "summary_en",
                    "note_ja",
                    "note_en",
                    "example_ja",
                    "example_en",
                    "preview",
                ];
                let mut unknown: Vec<_> = item_obj
                    .keys()
                    .filter(|key| !keys.contains(&key.as_str()))
                    .collect();
                unknown.sort();
                for key in unknown {
                    wp.push(problem(&format!("{path}.{key}"), "unknown_field", ""));
                }
                if !namespace.is_empty() && item["definition"]["namespace"] != namespace {
                    wp.push(problem(
                        &format!("{path}.definition.namespace"),
                        "namespace_differs_from_package",
                        namespace,
                    ));
                }
                let summary_ja = text(
                    &item["summary_ja"],
                    &format!("{path}.summary_ja"),
                    &mut wp,
                    8192,
                );
                let summary_en = text(
                    &item["summary_en"],
                    &format!("{path}.summary_en"),
                    &mut wp,
                    8192,
                );
                for (lang, v) in [("ja", &summary_ja), ("en", &summary_en)] {
                    if v.len() > 8192 {
                        wp.push(problem(
                            &format!("{path}.summary_{lang}"),
                            "text_too_long",
                            8192,
                        ));
                    }
                }
                if summary_ja.is_empty() && summary_en.is_empty() {
                    wp.push(problem(&format!("{path}.summary_ja"), "no_summary", ""));
                }
                let note_ja = text(&item["note_ja"], &format!("{path}.note_ja"), &mut wp, 2000);
                let note_en = text(&item["note_en"], &format!("{path}.note_en"), &mut wp, 2000);
                let ex_ja = text(
                    &item["example_ja"],
                    &format!("{path}.example_ja"),
                    &mut wp,
                    500,
                );
                let ex_en = text(
                    &item["example_en"],
                    &format!("{path}.example_en"),
                    &mut wp,
                    500,
                );
                let mut picture = Value::Null;
                if !stored && !item["preview"].is_null() {
                    let pp = format!("{path}.preview");
                    if item["preview"].as_str().is_none_or(|v| v.trim().is_empty()) {
                        wp.push(problem(&pp, "not_a_string", ""));
                    } else {
                        let named = s(&item["preview"]);
                        if let Some(map) = pictures {
                            if named.starts_with('/')
                                || named.replace('\\', "/").split('/').any(|p| p == "..")
                            {
                                wp.push(problem(&pp, "invalid_preview_path", named));
                            } else {
                                match map.get(named) {
                                    None => wp.push(problem(&pp, "preview_not_found", named)),
                                    Some(None) => {
                                        wp.push(problem(&pp, "image_too_large", MAX_PICTURE))
                                    }
                                    Some(Some(bytes)) => match plugin_picture::uploaded(bytes) {
                                        Ok(v) => picture = v,
                                        Err(mut p) => {
                                            p["path"] = json!(pp);
                                            wp.push(p);
                                        }
                                    },
                                }
                            }
                        } else {
                            wp.push(problem(&pp, "preview_needs_zip", ""));
                        }
                    }
                }
                let definition = &item["definition"];
                let ns = python_string_field(definition, "namespace");
                let heading = python_string_field(definition, "heading");
                let aliases: Vec<_> = definition["aliases"]
                    .as_array()
                    .map(|a| a.iter().filter_map(Value::as_str).collect())
                    .unwrap_or_default();
                let qualified = format!("{ns}.{heading}");
                let visible: Vec<_> = std::iter::once(qualified.clone())
                    .chain(aliases.iter().map(|a| format!("{ns}.{a}")))
                    .collect();
                let key = Sha256::digest(heading.as_bytes())
                    .iter()
                    .take(8)
                    .map(|b| format!("{b:02x}"))
                    .collect::<String>();
                let default_ja =
                    format!("{}.{}。", ns, aliases.first().copied().unwrap_or(&heading));
                let default_en = format!("{qualified}.");
                words.push(json!({"index":index,"definition":definition,"heading":heading,"summary_ja":summary_ja,"summary_en":summary_en,"note_ja":note_ja,"note_en":note_en,"example_ja":ex_ja,"example_en":ex_en,"draw_ja":if ex_ja.is_empty(){&default_ja}else{&ex_ja},"draw_en":if ex_en.is_empty(){&default_en}else{&ex_en},"aliases":aliases,"qualified_name":qualified,"visible_qualified_names":visible,"preview_key":key,"problems":wp,"picture":picture}));
            }
        }
    }
    if !blocking.is_empty() {
        blocking.extend(problems);
        return Err(blocking);
    }
    Ok(
        json!({"namespace":namespace,"name":name,"version":version,"description_ja":desc_ja,"description_en":desc_en,"authors":authors,"license":license,"problems":problems,"words":words}),
    )
}

fn summary(word: &Value, lang: &str) -> String {
    let first = s(&word[format!("summary_{lang}")]);
    if !first.is_empty() {
        first.to_owned()
    } else {
        s(&word[if lang == "ja" {
            "summary_en"
        } else {
            "summary_ja"
        }])
        .to_owned()
    }
}

fn start(input: &Value) -> Result<Value, Vec<Value>> {
    let (document, pictures) = if let Some(doc) = input["document"].as_str() {
        (doc.to_owned(), None)
    } else {
        let data = STANDARD
            .decode(s(&input["archive"]))
            .map_err(|_| vec![problem("", "invalid_zip", "")])?;
        let (doc, pics) = archive(&data)?;
        (doc, Some(pics))
    };
    let package = parse(&document, pictures.as_ref(), false)?;
    let words = package["words"].as_array().unwrap();
    let candidates:Vec<_>=words.iter().enumerate().map(|(i,w)|json!({"source_id":format!("word:{i}"),"definition_json":w["definition"].to_string(),"summary":summary(w,"en")})).collect();
    let payload = json!({"maximum_entries":320,"canonical":candidates,"legacy":[],"bundled_packages":[],"language":"en"});
    let resolved: Value = serde_json::from_slice(&crate::resolve_macro_catalog(
        serde_json::to_vec(&payload).unwrap(),
    ))
    .unwrap();
    let mut def_problems = vec![Vec::<Value>::new(); words.len()];
    let path_re = Regex::new(r":\d+:\d+$").unwrap();
    if let Some(diagnostics) = resolved["diagnostics"].as_array() {
        for diagnostic in diagnostics {
            let Some(i) = s(&diagnostic["source_id"])
                .strip_prefix("word:")
                .and_then(|x| x.parse::<usize>().ok())
                .filter(|i| *i < words.len())
            else {
                continue;
            };
            let base = format!("words[{}].definition", words[i]["index"]);
            if let Some(findings) = diagnostic["findings"].as_array().filter(|a| !a.is_empty()) {
                for finding in findings {
                    let path = path_re.replace(s(&finding["path"]), "");
                    let suffix = if path.is_empty() || path == "$" {
                        String::new()
                    } else if let Some(p) = path.strip_prefix('$') {
                        p.to_owned()
                    } else if path.starts_with('.') || path.starts_with('[') {
                        path.to_string()
                    } else {
                        format!(".{path}")
                    };
                    def_problems[i].push(problem(
                        &format!("{base}{suffix}"),
                        s(&finding["code"]),
                        "",
                    ));
                }
            } else {
                def_problems[i].push(problem(&base, s(&diagnostic["reason"]), ""));
            }
        }
    }
    let mut entries = vec![Value::Null; words.len()];
    let id = format!("{}.{}", s(&package["namespace"]), s(&package["name"]));
    if let Some(resolved_entries) = resolved["entries"].as_array() {
        for entry in resolved_entries {
            let Some(i) = s(&entry["source_id"])
                .strip_prefix("word:")
                .and_then(|x| x.parse::<usize>().ok())
                .filter(|i| *i < words.len())
            else {
                continue;
            };
            for name in std::iter::once(&entry["qualified_name"])
                .chain(entry["aliases"].as_array().into_iter().flatten())
            {
                if let Some(holder) = input["taken_names"][s(name)].as_str().filter(|h| *h != id) {
                    def_problems[i].push(problem(
                        &format!("words[{}].definition", words[i]["index"]),
                        "name_taken",
                        format!("{} ({holder})", s(name)),
                    ));
                }
            }
            entries[i] = entry.clone();
        }
    }
    let imported: Vec<_> = words
        .iter()
        .enumerate()
        .filter(|(i, _)| def_problems[*i].is_empty())
        .map(|(_, w)| json!({"definition":w["definition"],"summary":summary(w,"en")}))
        .collect();
    let draw:Vec<_>=words.iter().enumerate().filter(|(i,_)|def_problems[*i].is_empty()).flat_map(|(i,w)|["ja","en"].into_iter().map(move |lang|json!({"id":format!("{i}:{lang}"),"language":lang,"ddl":w[format!("draw_{lang}")]}))).collect();
    Ok(
        json!({"outcome":"ok","state":{"document":document,"package":package,"entries":entries,"definition_problems":def_problems},"draw":draw,"imported":imported}),
    )
}

fn finish(input: &Value) -> Result<Value, ()> {
    let state = &input["state"];
    let package = &state["package"];
    let words = package["words"].as_array().ok_or(())?;
    let drawings = input["drawings"].as_array().ok_or(())?;
    let defs = state["definition_problems"]
        .as_array()
        .filter(|x| x.len() == words.len())
        .ok_or(())?;
    let entries = state["entries"]
        .as_array()
        .filter(|x| x.len() == words.len())
        .ok_or(())?;
    let mut reports = Vec::new();
    let mut pictures = serde_json::Map::new();
    for (i, w) in words.iter().enumerate() {
        let mut problems = w["problems"].as_array().ok_or(())?.clone();
        let def = defs[i].as_array().ok_or(())?;
        problems.extend(def.clone());
        let mut picture = w["picture"].clone();
        if def.is_empty() {
            for lang in ["ja", "en"] {
                let id = format!("{i}:{lang}");
                let drawing = drawings.iter().find(|d| s(&d["id"]) == id).ok_or(())?;
                let reasons = drawing["reasons"].as_array().ok_or(())?;
                if !reasons.is_empty() || drawing["marks"].as_u64().unwrap_or(0) == 0 {
                    let reasons: Vec<&str> = if reasons.is_empty() {
                        vec!["example_draws_nothing"]
                    } else {
                        reasons.iter().map(s).collect()
                    };
                    for reason in reasons {
                        problems.push(problem(
                            &format!("words[{}].example_{lang}", w["index"]),
                            reason,
                            "",
                        ));
                    }
                } else if lang == "ja" && picture.is_null() {
                    picture = plugin_picture::drawn(s(&drawing["svg"])).map_err(|_| ())?;
                }
            }
        }
        if !picture.is_null() {
            pictures.insert(s(&w["preview_key"]).to_owned(), picture);
        }
        let aliases: Vec<_> = w["visible_qualified_names"]
            .as_array()
            .ok_or(())?
            .iter()
            .skip(1)
            .cloned()
            .collect();
        reports.push(json!({"heading":w["heading"],"qualified_name":w["qualified_name"],"aliases":aliases,"summary_ja":summary(w,"ja"),"summary_en":summary(w,"en"),"note_ja":w["note_ja"],"note_en":w["note_en"],"example_ja":w["draw_ja"],"example_en":w["draw_en"],"digest":s(&entries[i]["digest"]),"preview_source":if w["picture"].is_null(){"drawn"}else{"file"},"problems":problems}));
    }
    let package_problems = package["problems"].as_array().ok_or(())?;
    let ok = package_problems.is_empty()
        && reports
            .iter()
            .all(|r| r["problems"].as_array().is_some_and(Vec::is_empty));
    let report = json!({"ok":ok,"id":format!("{}.{}",s(&package["namespace"]),s(&package["name"])),"namespace":package["namespace"],"name":package["name"],"version":package["version"],"description_ja":package["description_ja"],"description_en":package["description_en"],"problems":package_problems,"words":reports});
    Ok(json!({"outcome":"ok","report":report,"text":state["document"],"pictures":pictures}))
}

fn ordered_object(value: &Value, keys: &[&str]) -> String {
    let fields: Vec<_> = keys
        .iter()
        .map(|key| format!("{}:{}", json!(key), value[*key]))
        .collect();
    format!("{{{}}}", fields.join(","))
}

fn encode_finished(output: &Value) -> Option<Vec<u8>> {
    let report = &output["report"];
    let words = report["words"].as_array()?;
    let word_keys = [
        "heading",
        "qualified_name",
        "aliases",
        "summary_ja",
        "summary_en",
        "note_ja",
        "note_en",
        "example_ja",
        "example_en",
        "digest",
        "preview_source",
        "problems",
    ];
    let word_json = words
        .iter()
        .map(|w| ordered_object(w, &word_keys))
        .collect::<Vec<_>>()
        .join(",");
    let report_keys = [
        "ok",
        "id",
        "namespace",
        "name",
        "version",
        "description_ja",
        "description_en",
        "problems",
    ];
    let mut report_json = ordered_object(report, &report_keys);
    report_json.pop();
    report_json.push_str(&format!(",\"words\":[{word_json}]}}"));
    Some(
        format!(
            "{{\"outcome\":\"ok\",\"report\":{report_json},\"text\":{},\"pictures\":{}}}",
            output["text"], output["pictures"]
        )
        .into_bytes(),
    )
}

#[uniffi::export]
pub fn plugin_package(input_bytes: Vec<u8>) -> Vec<u8> {
    let output = std::panic::catch_unwind(|| {
        let input: Value = serde_json::from_slice(&input_bytes).map_err(|_| ())?;
        let result = match s(&input["action"]) {
            "check_start" => {
                if input["document"].as_str().is_some() == input["archive"].as_str().is_some()
                    || !input["taken_names"].is_object()
                {
                    return Err(());
                }
                match start(&input) {
                    Ok(v) => v,
                    Err(p) => refused(p),
                }
            }
            "check_finish" => finish(&input)?,
            "read_stored" => match parse(input["document"].as_str().ok_or(())?, None, true) {
                Ok(mut p) => {
                    if let Some(words) = p["words"].as_array_mut() {
                        for word in words {
                            if let Some(fields) = word.as_object_mut() {
                                fields.remove("picture");
                                fields.remove("heading");
                                fields.remove("draw_ja");
                                fields.remove("draw_en");
                            }
                        }
                    }
                    json!({"outcome":"ok","package":p})
                }
                Err(p) => refused(p),
            },
            "fit_picture" => {
                let data = STANDARD
                    .decode(input["png"].as_str().ok_or(())?)
                    .map_err(|_| ())?;
                match plugin_picture::uploaded(&data) {
                    Ok(mut p) => {
                        p["outcome"] = json!("ok");
                        p
                    }
                    Err(p) => refused(vec![p]),
                }
            }
            _ => return Err(()),
        };
        Ok::<_, ()>(result)
    })
    .ok()
    .and_then(Result::ok)
    .unwrap_or_else(|| json!({"error":"invalid_plugin_package_input"}));
    if output["outcome"] == "ok"
        && output.get("report").is_some()
        && let Some(encoded) = encode_finished(&output)
    {
        return encoded;
    }
    serde_json::to_vec(&output)
        .unwrap_or_else(|_| br#"{"error":"invalid_plugin_package_input"}"#.to_vec())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn call(input: Value) -> Value {
        serde_json::from_slice(&plugin_package(serde_json::to_vec(&input).unwrap())).unwrap()
    }

    #[test]
    fn package_checks_continue_for_nonblocking_issues_and_round_trip() {
        let document = include_str!("../../../../docs/plugins/sky-nihonga/package.json");
        let stored = call(json!({"action":"read_stored","document":document}));
        assert_eq!(stored["outcome"], "ok");
        let start = call(json!({"action":"check_start","document":document,"taken_names":{}}));
        assert_eq!(start["outcome"], "ok");
        assert!(!start["draw"].as_array().unwrap().is_empty());
        let drawings:Vec<_> = start["draw"].as_array().unwrap().iter().map(|d|json!({
            "id":d["id"],"svg":"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"100\" height=\"100\"><rect width=\"100\" height=\"100\" fill=\"white\"/><circle cx=\"50\" cy=\"50\" r=\"20\" fill=\"black\"/></svg>","marks":1,"reasons":[]
        })).collect();
        let end = call(json!({"action":"check_finish","state":start["state"],"drawings":drawings}));
        assert_eq!(end["outcome"], "ok");
        assert_eq!(end["text"], document);
        let encoded = String::from_utf8(encode_finished(&end).unwrap()).unwrap();
        let report = encoded.split("\"report\":{").nth(1).unwrap();
        assert!(report.starts_with("\"ok\":"));
        assert!(report.find("\"id\":").unwrap() < report.find("\"namespace\":").unwrap());
        assert!(report.find("\"problems\":").unwrap() < report.find("\"words\":").unwrap());
        assert!(!end["pictures"].as_object().unwrap().is_empty());
        let malformed = call(json!({"action":"check_start","document":"{}","taken_names":{}}));
        assert_eq!(malformed["outcome"], "refused");
        assert_eq!(malformed["problems"][0]["code"], "invalid_identifier");
        assert_eq!(malformed["problems"][2]["code"], "no_words");
    }

    #[test]
    fn zipped_package_and_bad_picture_have_bounded_results() {
        let zip = include_bytes!("../../../../docs/plugins/sky-nihonga.zip");
        let start =
            call(json!({"action":"check_start","archive":STANDARD.encode(zip),"taken_names":{}}));
        assert_eq!(start["outcome"], "ok");
        assert!(
            start["state"]["package"]["words"]
                .as_array()
                .unwrap()
                .iter()
                .any(|w| w["picture"].is_object())
        );
        let bad = call(json!({"action":"fit_picture","png":STANDARD.encode(b"not png")}));
        assert_eq!(bad["problems"][0]["code"], "not_a_png");
    }

    #[test]
    fn shape_findings_and_preview_boundaries_keep_their_paths() {
        let doc = include_str!("../../../../docs/plugins/sky-nihonga/package.json");
        let mut raw: Value = serde_json::from_str(doc).unwrap();
        raw["extra_z"] = json!(1);
        raw["extra_a"] = json!(1);
        raw["schema"] = json!("wrong");
        raw["version"] = json!("wrong");
        raw["description_ja"] = json!(false);
        raw["authors"] = json!([1]);
        raw["words"][0]["summary_ja"] = json!("");
        raw["words"][0]["summary_en"] = json!("");
        raw["words"][0]["preview"] = json!("missing.png");
        let output = call(json!({"action":"read_stored","document":raw.to_string()}));
        assert_eq!(output["outcome"], "ok");
        let problems = output["package"]["problems"].as_array().unwrap();
        assert_eq!(problems[0]["path"], "extra_a");
        assert_eq!(problems[1]["path"], "extra_z");
        for code in [
            "unknown_field",
            "wrong_schema",
            "invalid_semantic_version",
            "not_a_string",
            "not_a_list_of_strings",
        ] {
            assert!(problems.iter().any(|p| p["code"] == code), "{code}");
        }
        assert!(
            output["package"]["words"][0]["problems"]
                .as_array()
                .unwrap()
                .iter()
                .any(|p| p["code"] == "no_summary")
        );
        let start =
            call(json!({"action":"check_start","document":raw.to_string(),"taken_names":{}}));
        assert!(
            start["state"]["package"]["words"][0]["problems"]
                .as_array()
                .unwrap()
                .iter()
                .any(|p| p["code"] == "preview_needs_zip")
        );
        let invalid = call(json!({"action":"read_stored","document":"{\n invalid"}));
        let detail = invalid["problems"][0]["detail"].as_str().unwrap();
        assert!(detail.contains(" (line 2, column "));
    }
}
