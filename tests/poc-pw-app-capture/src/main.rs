// ============================================================================
// LOCKED pipewire-rs API — validated against `pipewire = "0.8"` (resolved 0.8.0,
// libpipewire-0.3 = 1.6.3) on this machine. Task 2 copies these verbatim.
//
// Crate / imports:
//   pipewire = "0.8"            // Cargo.toml (resolves to 0.8.0)
//   use pipewire::{context::Context, main_loop::MainLoop, properties::properties};
//   use pipewire::types::ObjectType;
//
// Boilerplate (all infallible-or-Result, .expect() shown):
//   pipewire::init();
//   let mainloop = MainLoop::new(None).expect(..);                  // Option<&Properties>
//   let context  = Context::new(&mainloop).expect(..);             // &MainLoop
//   let core     = context.connect(None).expect(..);              // Option<Properties>
//   let registry = core.get_registry().expect(..);
//   core.clone()  // Core is Clone (Rc-backed) — clone into the registry closure.
//
// create_object — generic over the proxy type, returns Result<P, Error>:
//   let sink = core.create_object::<pipewire::node::Node>(
//       "adapter",                       // factory name (&str)
//       &properties! { "k" => "v", .. }, // &Properties via properties!{} macro
//   ).expect(..);                        // -> Node proxy; keep alive for loop lifetime
//
//   let link = core.create_object::<pipewire::link::Link>(
//       "link-factory",
//       &properties! { .. },
//   );                                   // -> Result<Link, Error>
//
// Null-sink factory props (Audio/Sink, stereo):
//   "factory.name" => "support.null-audio-sink"
//   "media.class"  => "Audio/Sink"
//   "node.name"    => <sink-name>
//   "node.virtual" => "true"
//   "audio.channels" => "2"
//   "audio.position" => "FL,FR"
//
// link-factory props (BOTH node AND port ids — the safe OBS form):
//   "link.output.node" => <out node id as String>
//   "link.output.port" => <out port id as String>
//   "link.input.node"  => <sink node id as String>
//   "link.input.port"  => <sink input port id as String>
//   "object.linger"    => "false"        // link dies with this client
//
// Registry listener:
//   let _listener = registry.add_listener_local()
//       .global(move |g| { /* g: &GlobalObject<&DictRef> */ ... })
//       .register();                     // keep _listener alive for loop lifetime
//   GlobalObject fields used: g.id (u32), g.type_ (ObjectType), g.props (Option<&DictRef>).
//   DictRef::get(&self, key) -> Option<&str>.
//
// mainloop.run();  // blocks; Ctrl-C to exit. Non-linger sink + links auto-destroyed
//                  // when this client disconnects (verified: pw-cli ls Node -> 0).
//
// Proxy lifetimes: create_object returns a Proxy that must be kept alive or the
// object is destroyed. Sink is held in `_sink`; per-link proxies are std::mem::forget'd
// (intentional leak for the POC — Task 2 should store them in a Vec instead).
//
// ISOLATION PROVEN: target=pw-play, decoy=paplay. Capture sink with
//   pw-record -P 'stream.capture.sink=true' --target=<sink>
//   Check A (decoy-only)  -> max amp 0.000000  (excluded)
//   Check B (target-only) -> max amp 0.500000  (captured)
// ============================================================================
use std::cell::RefCell;
use std::collections::{HashMap, HashSet};
use std::rc::Rc;

use pipewire::{context::Context, main_loop::MainLoop, properties::properties};
use pipewire::types::ObjectType;

// Run: cargo run -- --match firefox [--match mpv] [--sink-name dictee_cap_poc]
#[derive(Default)]
struct State {
    sink_id: Option<u32>,
    sink_in_ports: HashMap<String, u32>,             // channel -> sink input port id
    target_nodes: HashSet<u32>,                      // matched app node ids
    all_out_ports: HashMap<u32, Vec<(u32, String)>>, // node id -> [(out port id, channel)]
    linked: HashSet<u32>,                            // out port ids already linked
}

fn main() {
    let mut matches: Vec<String> = Vec::new();
    let mut sink_name = "dictee_cap_poc".to_string();
    let mut it = std::env::args().skip(1);
    while let Some(a) = it.next() {
        match a.as_str() {
            "--match" => { if let Some(m) = it.next() { matches.push(m.to_lowercase()); } }
            "--sink-name" => { if let Some(s) = it.next() { sink_name = s; } }
            _ => {}
        }
    }
    if matches.is_empty() { matches.push("firefox".into()); }
    let matches = Rc::new(matches);
    let sink_name = Rc::new(sink_name);

    pipewire::init();
    let mainloop = MainLoop::new(None).expect("mainloop");
    let context = Context::new(&mainloop).expect("context");
    let core = context.connect(None).expect("connect");
    let registry = core.get_registry().expect("registry");

    // Virtual capture sink — auto-destroyed when this client exits (non-linger).
    let _sink = core.create_object::<pipewire::node::Node>(
        "adapter",
        &properties! {
            "factory.name" => "support.null-audio-sink",
            "media.class" => "Audio/Sink",
            "node.name" => sink_name.as_str(),
            "node.virtual" => "true",
            "audio.channels" => "2",
            "audio.position" => "FL,FR",
        },
    ).expect("create sink");

    let state = Rc::new(RefCell::new(State::default()));
    let st = state.clone();
    let core_cb = core.clone();
    let m = matches.clone();
    let sn = sink_name.clone();

    let _listener = registry.add_listener_local()
        .global(move |g| {
            let props = match g.props { Some(p) => p, None => return };
            match g.type_ {
                ObjectType::Node => {
                    if props.get("node.name") == Some(sn.as_str()) {
                        st.borrow_mut().sink_id = Some(g.id);
                    } else if props.get("media.class") == Some("Stream/Output/Audio") {
                        let app = props.get("application.name").unwrap_or("").to_lowercase();
                        let bin = props.get("application.process.binary").unwrap_or("").to_lowercase();
                        let nn  = props.get("node.name").unwrap_or("").to_lowercase();
                        if m.iter().any(|x| app.contains(x) || bin.contains(x) || nn.contains(x)) {
                            let ports = {
                                let mut s = st.borrow_mut();
                                s.target_nodes.insert(g.id);
                                s.all_out_ports.get(&g.id).cloned().unwrap_or_default()
                            };
                            link_ports(&core_cb, &st, g.id, &ports);
                            println!("[poc] target node {} ({app}/{bin})", g.id);
                        }
                    }
                }
                ObjectType::Port => {
                    let nid = match props.get("node.id").and_then(|s| s.parse::<u32>().ok()) {
                        Some(n) => n, None => return,
                    };
                    let dir = props.get("port.direction").unwrap_or("");
                    let chan = props.get("audio.channel").unwrap_or("MONO").to_string();
                    if dir == "in" {
                        let mut s = st.borrow_mut();
                        if Some(nid) == s.sink_id { s.sink_in_ports.insert(chan, g.id); }
                    } else if dir == "out" {
                        let is_target = {
                            let mut s = st.borrow_mut();
                            s.all_out_ports.entry(nid).or_default().push((g.id, chan.clone()));
                            s.target_nodes.contains(&nid)
                        };
                        if is_target { link_ports(&core_cb, &st, nid, &[(g.id, chan)]); }
                    }
                }
                _ => {}
            }
        })
        .register();

    println!("[poc] sink={} matches={:?} — play the app(s), then capture:", sink_name, matches);
    println!("[poc]   pw-record -P 'stream.capture.sink=true' --target={} /tmp/poc.wav", sink_name);
    mainloop.run();
}

fn link_ports(core: &pipewire::core::Core, st: &Rc<RefCell<State>>, node_id: u32, ports: &[(u32, String)]) {
    let mut s = st.borrow_mut();
    let sink_id = match s.sink_id { Some(id) => id, None => return };
    if s.sink_in_ports.is_empty() { return; }
    for (out_port, chan) in ports {
        if s.linked.contains(out_port) { continue; }
        let in_port = match s.sink_in_ports.get(chan).or_else(|| s.sink_in_ports.get("FL")).copied() {
            Some(p) => p, None => continue,
        };
        let link = core.create_object::<pipewire::link::Link>(
            "link-factory",
            &properties! {
                "link.output.node" => node_id.to_string(),
                "link.output.port" => out_port.to_string(),
                "link.input.node" => sink_id.to_string(),
                "link.input.port" => in_port.to_string(),
                "object.linger" => "false",
            },
        );
        match link {
            Ok(l) => { s.linked.insert(*out_port); std::mem::forget(l);
                       println!("[poc] linked node {node_id} port {out_port} ({chan}) -> {in_port}"); }
            Err(e) => println!("[poc] link failed: {e}"),
        }
    }
}
