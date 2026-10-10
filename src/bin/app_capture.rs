//! dictee-app-capture — maintain a virtual PipeWire source fed by a target
//! application's audio streams (and optionally the mic), event-driven, so the
//! meeting window can record ONLY that app with a plain `pw-record --target`.
//!
//! Links the app's output ports into a private virtual source instead of moving
//! the stream, so the app keeps playing on the user's speakers. A source, not a
//! sink: WirePlumber 0.5.11+ (linking/mpris-pause.lua) pauses every MPRIS player
//! linked to a sink that goes away, so a private sink paused the recorded player
//! each time a capture stopped. A source is never a player's output to it.
//!
//! Usage:
//!   dictee-app-capture --source-name <name> --description <text> --match <key>
//!                      [--match <key>…] [--include-mic]
//!
//! Prints `READY <source_id>` to stdout once the source and its input ports exist.
//! Runs until SIGINT/SIGTERM, then quits the main loop; the non-linger source and
//! all links are destroyed automatically when this client disconnects.

use std::cell::RefCell;
use std::collections::{HashMap, HashSet};
use std::io::Write;
use std::rc::Rc;

use pipewire::loop_::Signal;
use pipewire::types::ObjectType;
use pipewire::{context::Context, main_loop::MainLoop, properties::properties};

struct Args {
    source_name: String,
    description: String,
    matches: Vec<String>,
    include_mic: bool,
}

fn parse_args() -> Args {
    let mut source_name = "dictee_capture".to_string();
    let mut description = "Dictee capture".to_string();
    let mut matches = Vec::new();
    let mut include_mic = false;
    let mut it = std::env::args().skip(1);
    while let Some(a) = it.next() {
        match a.as_str() {
            "--source-name" => {
                if let Some(s) = it.next() {
                    source_name = s;
                }
            }
            "--description" => {
                if let Some(s) = it.next() {
                    description = s;
                }
            }
            "--match" => {
                if let Some(m) = it.next() {
                    matches.push(m.to_lowercase());
                }
            }
            "--include-mic" => include_mic = true,
            other => eprintln!("[app-capture] ignoring arg {other}"),
        }
    }
    if matches.is_empty() && !include_mic {
        eprintln!("[app-capture] need at least one --match or --include-mic");
        std::process::exit(2);
    }
    Args {
        source_name,
        description,
        matches,
        include_mic,
    }
}

#[derive(Default)]
struct State {
    source_id: Option<u32>,
    source_in_ports: HashMap<String, u32>, // channel -> source input port id
    ready_printed: bool,
    target_nodes: HashSet<u32>, // matched app/mic node ids
    all_out_ports: HashMap<u32, Vec<(u32, String)>>, // node id -> [(out port id, channel)]
    linked: HashSet<u32>,       // out port ids already linked
    links: Vec<pipewire::link::Link>, // keep link proxies alive for the loop lifetime
}

fn main() {
    let args = parse_args();
    let matches = Rc::new(args.matches);
    let source_name = Rc::new(args.source_name);
    let include_mic = args.include_mic;

    pipewire::init();
    let mainloop = MainLoop::new(None).expect("mainloop");

    // Block SIGINT/SIGTERM on this (main) thread BEFORE connecting to PipeWire.
    // `core.connect()` spawns a data-loop thread that inherits this mask, so both
    // threads keep the signals blocked. spa's signal sources (added below) consume
    // them via signalfd on the main loop. Without this block the data thread leaves
    // the signals unblocked, the kernel delivers them there, and the default
    // disposition kills the process (exit 130/143) before the signalfd fires.
    block_term_signals();

    let context = Context::new(&mainloop).expect("context");
    let core = context.connect(None).expect("connect");
    let registry = core.get_registry().expect("registry");

    // Quit the loop on SIGINT/SIGTERM so teardown (drop of core → source + links)
    // happens cleanly inside the loop. SignalSources are #[must_use] + Drop, so
    // they must stay alive for the loop's lifetime.
    let ml_int = mainloop.clone();
    let _sig_int = mainloop
        .loop_()
        .add_signal_local(Signal::SIGINT, move || ml_int.quit());
    let ml_term = mainloop.clone();
    let _sig_term = mainloop
        .loop_()
        .add_signal_local(Signal::SIGTERM, move || ml_term.quit());

    // Virtual capture source, auto-destroyed when this client exits (non-linger).
    // Its input ports take the app's links; recorders and meters read it like a
    // microphone, and its volume applies to what they read.
    let _source = core
        .create_object::<pipewire::node::Node>(
            "adapter",
            &properties! {
                "factory.name" => "support.null-audio-sink",
                "media.class" => "Audio/Source/Virtual",
                "node.name" => source_name.as_str(),
                "node.description" => args.description.as_str(),
                "node.virtual" => "true",
                // What recorders read carries the raw signal unless asked
                // otherwise: without this the source's volume (the meeting
                // window's 🔊 slider) changed nothing.
                "monitor.channel-volumes" => "true",
                "audio.channels" => "2",
                "audio.position" => "FL,FR",
            },
        )
        .expect("create source");

    let state = Rc::new(RefCell::new(State::default()));
    let st = state.clone();
    let core_cb = core.clone();
    let m = matches.clone();
    let sn = source_name.clone();

    let _listener = registry
        .add_listener_local()
        .global(move |g| {
            let props = match g.props {
                Some(p) => p,
                None => return,
            };
            match g.type_ {
                ObjectType::Node => {
                    if props.get("node.name") == Some(sn.as_str()) {
                        st.borrow_mut().source_id = Some(g.id);
                    } else if props.get("media.class") == Some("Stream/Output/Audio") {
                        let app = props.get("application.name").unwrap_or("").to_lowercase();
                        // Match on the FIRST WORD of application.name only — the exact
                        // token dictee-audio-sources advertises as 'app:<first-word>'
                        // (a.lower().split()[0]). Substring matching across name /
                        // binary / node.name was too broad: two apps sharing a token,
                        // or a node.name fragment, were captured together.
                        let app_first = app.split_whitespace().next().unwrap_or("");
                        if !app_first.is_empty() && m.iter().any(|x| x.as_str() == app_first)
                        {
                            let ports = {
                                let mut s = st.borrow_mut();
                                s.target_nodes.insert(g.id);
                                s.all_out_ports.get(&g.id).cloned().unwrap_or_default()
                            };
                            link_ports(&core_cb, &st, g.id, &ports);
                            eprintln!("[app-capture] target app node {} ({app})", g.id);
                        }
                    } else if include_mic && props.get("media.class") == Some("Audio/Source") {
                        // Default microphone: an Audio/Source whose node.name is not a
                        // monitor of a sink. Link its output ports into the capture source.
                        let nn = props.get("node.name").unwrap_or("");
                        if !nn.ends_with(".monitor") {
                            let ports = {
                                let mut s = st.borrow_mut();
                                s.target_nodes.insert(g.id);
                                s.all_out_ports.get(&g.id).cloned().unwrap_or_default()
                            };
                            link_ports(&core_cb, &st, g.id, &ports);
                            eprintln!("[app-capture] target mic node {} ({nn})", g.id);
                        }
                    }
                }
                ObjectType::Port => {
                    let nid = match props.get("node.id").and_then(|s| s.parse::<u32>().ok()) {
                        Some(n) => n,
                        None => return,
                    };
                    let dir = props.get("port.direction").unwrap_or("");
                    let chan = props.get("audio.channel").unwrap_or("MONO").to_string();
                    if dir == "in" {
                        let ready = {
                            let mut s = st.borrow_mut();
                            if Some(nid) == s.source_id {
                                s.source_in_ports.insert(chan, g.id);
                            }
                            s.source_id.is_some()
                                && !s.source_in_ports.is_empty()
                                && !s.ready_printed
                        };
                        if ready {
                            print_ready(&st);
                            drain_pending(&core_cb, &st);
                        }
                    } else if dir == "out" {
                        let is_target = {
                            let mut s = st.borrow_mut();
                            s.all_out_ports
                                .entry(nid)
                                .or_default()
                                .push((g.id, chan.clone()));
                            s.target_nodes.contains(&nid)
                        };
                        if is_target {
                            link_ports(&core_cb, &st, nid, &[(g.id, chan)]);
                        }
                    }
                }
                _ => {}
            }
        })
        .register();

    mainloop.run();
}

/// Block SIGINT and SIGTERM on the calling thread so the PipeWire data thread
/// (spawned by `core.connect()`) inherits the block and the main loop's signalfd
/// sources can consume them. Idempotent and safe to call once at startup.
fn block_term_signals() {
    unsafe {
        let mut set: libc::sigset_t = std::mem::zeroed();
        libc::sigemptyset(&mut set);
        libc::sigaddset(&mut set, libc::SIGINT);
        libc::sigaddset(&mut set, libc::SIGTERM);
        libc::pthread_sigmask(libc::SIG_BLOCK, &set, std::ptr::null_mut());
    }
}

/// Print `READY <source_id>` to stdout exactly once and flush.
fn print_ready(st: &Rc<RefCell<State>>) {
    let mut s = st.borrow_mut();
    if s.ready_printed {
        return;
    }
    if let Some(id) = s.source_id {
        s.ready_printed = true;
        let mut out = std::io::stdout();
        let _ = writeln!(out, "READY {id}");
        let _ = out.flush();
    }
}

/// Link any already-seen out-ports of known target nodes (in case the target
/// node + its ports appeared before the source's input ports were ready).
fn drain_pending(core: &pipewire::core::Core, st: &Rc<RefCell<State>>) {
    let pending: Vec<(u32, Vec<(u32, String)>)> = {
        let s = st.borrow();
        s.target_nodes
            .iter()
            .filter_map(|nid| s.all_out_ports.get(nid).map(|p| (*nid, p.clone())))
            .collect()
    };
    for (nid, ports) in pending {
        link_ports(core, st, nid, &ports);
    }
}

fn link_ports(
    core: &pipewire::core::Core,
    st: &Rc<RefCell<State>>,
    node_id: u32,
    ports: &[(u32, String)],
) {
    let mut s = st.borrow_mut();
    let source_id = match s.source_id {
        Some(id) => id,
        None => return,
    };
    if s.source_in_ports.is_empty() {
        return;
    }
    for (out_port, chan) in ports {
        if s.linked.contains(out_port) {
            continue;
        }
        let in_port = match s
            .source_in_ports
            .get(chan)
            .or_else(|| s.source_in_ports.get("FL"))
            .copied()
        {
            Some(p) => p,
            None => continue,
        };
        let link = core.create_object::<pipewire::link::Link>(
            "link-factory",
            &properties! {
                "link.output.node" => node_id.to_string(),
                "link.output.port" => out_port.to_string(),
                "link.input.node" => source_id.to_string(),
                "link.input.port" => in_port.to_string(),
                "object.linger" => "false",
            },
        );
        match link {
            Ok(l) => {
                s.linked.insert(*out_port);
                s.links.push(l);
                eprintln!("[app-capture] linked node {node_id} port {out_port} ({chan}) -> {in_port}");
            }
            Err(e) => eprintln!("[app-capture] link failed: {e}"),
        }
    }
}
