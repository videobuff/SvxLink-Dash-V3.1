// SPDX-License-Identifier: GPL-2.0-or-later
// SvxLink 26.05.2 extension: priority announcements without module disconnection.
#include <RepeaterLogic.h>
#include <Module.h>
#include <AsyncAudioSelector.h>
#include <AsyncAudioValve.h>
#include <AsyncTimer.h>
#include <chrono>
#include <fstream>
#include <iostream>
#include <sstream>
#include <regex>
#include <cstdio>
#include <cstdint>
#include <sys/stat.h>

class Pi3tweLogic : public RepeaterLogic {
 public:
  bool initialize(Async::Config& config, const std::string& logic_name) override {
    if (!RepeaterLogic::initialize(config, logic_name)) return false;
    config.getValue(logic_name, "PI3TWE_SPOOL", spool_);
    config.getValue(logic_name, "PI3TWE_STATUS", status_);
    config.getValue(logic_name, "PI3TWE_RADIO_ENABLED", radio_);
    if (spool_.empty() || status_.empty()) return false;
    auto* selector = pi3tweLiveAudio();
    // Gate immediately before the mixer, after the live-audio FIFO, so queued
    // RX/module audio cannot leak into the news announcement.
    auto* state_detector = dynamic_cast<Async::AudioSource*>(selector->sink());
    auto* live = state_detector ? dynamic_cast<Async::AudioSource*>(state_detector->sink()) : nullptr;
    if (!live || !live->sink()) return false;
    auto* sink = live->sink();
    bool managed = live->sinkManaged();
    live->unregisterSink();
    gate_ = new Async::AudioValve;
    gate_->setBlockWhenClosed(false); // Discard live audio, never stall EchoLink.
    gate_->registerSink(sink, managed);
    live->registerSink(gate_, true);
    gate_->setOpen(radio_);
    if (!radio_) setTxCtrlMode(Tx::TX_OFF);
    timer_.setTimeout(100);
    timer_.expired.connect([this](Async::Timer*) { tick(); });
    timer_.setEnable(false);
    std::ofstream(status_ + "/ready") << "SvxLink native audio logic 26.05.2\n";
    std::ofstream(status_ + "/call-test-ready") << "CALL RPTR\n";
    return true;
  }

  void processEvent(const std::string& event, const Module* module = nullptr) override {
    // Keep protocol/module lifecycles alive; suppress only their audible events.
    if ((news_ || !radio_) && event.rfind("pi3twe_", 0) != 0) return;
    RepeaterLogic::processEvent(event, module);
  }

 protected:
  void commandPtyCmdReceived(const void* buffer, size_t count) override {
    std::string line(static_cast<const char*>(buffer), count);
    std::istringstream input(line);
    std::string command, id, extra;
    input >> command >> id;
    if (!std::regex_match(id, std::regex("[a-f0-9]{32}"))) return;
    if (command == "NEWS") {
      unsigned intro_ms = 0, news_ms = 0;
      if (!(input >> intro_ms >> news_ms) || (input >> extra) || intro_ms > 20000 || !news_ms || news_ms > 1800000) {
        reply(id, "error"); return;
      }
      if (news_ || !radio_) { reply(id, news_ ? "busy" : "power_off"); return; }
      std::string file = spool_ + "/" + id + ".wav";
      if (!validWav(file, 2 * intro_ms + news_ms)) { reply(id, "error"); return; }
      // Cancel pending ID/effect audio, preserving active modules and connections.
      clearPendingSamples();
      news_ = true;
      job_ = id;
      intro_ms_ = intro_ms;
      news_ms_ = news_ms;
      gate_->setOpen(false);
      enableRgrSoundTimer(false);
      start_ = std::chrono::steady_clock::now();
      reply(job_, "before_beeps");
      timer_.setEnable(true);
      setEventVariable("Pi3twe::news_file", file);
      processEvent("pi3twe_news");
    } else if (command == "CALL") {
      if (input >> extra) { reply(id, "error"); return; }
      if (news_ || !radio_) { reply(id, news_ ? "busy" : "power_off"); return; }
      clearPendingSamples();
      news_ = true; // The same exclusive local announcement lane as news.
      call_test_ = true;
      job_ = id;
      gate_->setOpen(false);
      enableRgrSoundTimer(false);
      start_ = std::chrono::steady_clock::now();
      reply(job_, "call");
      timer_.setEnable(true);
      // Local MsgHandler -> TX mixer; never the RX -> EchoLink module path.
      processEvent("pi3twe_call");
    } else if (command == "STATUS") {
      reply(id, "done");
    } else if (command == "CANCEL") {
      if (news_ && id == job_) finish("cancelled");
      else reply(id, "idle");
    } else if (command == "RADIO") {
      unsigned enabled = 0;
      if (!(input >> enabled) || enabled > 1 || (input >> extra)) { reply(id, "error"); return; }
      radio_ = enabled;
      if (!radio_) {
        if (news_) finish("cancelled");
        gate_->setOpen(false);
        setTxCtrlMode(Tx::TX_OFF);
      } else {
        gate_->setOpen(!news_);
        setTxCtrlMode(Tx::TX_AUTO);
      }
      reply(id, "done");
    } else if (command == "POLICY") {
      std::string callsign; unsigned minutes = 0;
      if (!(input >> callsign >> minutes) || (input >> extra) || minutes < 1 || minutes > 60 ||
          !std::regex_match(callsign, std::regex("[A-Z0-9]{3,12}(/[A-Z0-9]{1,6})?"))) { reply(id, "error"); return; }
      if (news_) { reply(id, "busy"); return; }
      pi3tweCallsign(callsign);
      processEvent("pi3twe_policy " + std::to_string(minutes));
      reply(id, "done");
    } else {
      reply(id, "error");
    }
  }

  void allMsgsWritten() override {
    if (finishing_) { pi3tweEndAnnouncement(); return; }
    if (news_) { finish("done"); return; }
    RepeaterLogic::allMsgsWritten();
  }

 private:
  Async::AudioValve* gate_ = nullptr; // Owned by the existing SvxLink pipeline.
  Async::Timer timer_{100, Async::Timer::TYPE_PERIODIC, false};
  bool news_ = false, radio_ = true, finishing_ = false, call_test_ = false;
  std::string spool_, status_, job_;
  unsigned intro_ms_ = 0, news_ms_ = 0;
  std::chrono::steady_clock::time_point start_;

  void reply(const std::string& id, const std::string& phase) {
    std::string file = status_ + "/" + id + ".json";
    std::ofstream output(file + ".tmp");
    output << "{\"job\":\"" << id << "\",\"phase\":\"" << phase
           << "\",\"active_module\":\"" << (activeModule() ? activeModule()->name() : "")
           << "\",\"module_instance\":" << reinterpret_cast<uintptr_t>(activeModule()) << "}\n";
    output.close();
    if (!output || std::rename((file + ".tmp").c_str(), file.c_str()) != 0)
      std::cerr << "PI3TWE: cannot write command status" << std::endl;
    if (id == job_) {
      std::string current = status_ + "/current.json";
      std::ofstream state(current + ".tmp");
      state << "{\"job\":\"" << id << "\",\"phase\":\"" << phase << "\"}\n";
      state.close();
      std::rename((current + ".tmp").c_str(), current.c_str());
    }
  }

  void finish(const std::string& phase) {
    if (!news_) return;
    finishing_ = true;
    news_ = false; // Clear before cancelling the queue: flush callbacks re-enter.
    timer_.setEnable(false);
    call_test_ = false;
    if (phase != "done") clearPendingSamples();
    gate_->setOpen(radio_);
    pi3tweEndAnnouncement();
    reply(job_, phase);
    job_.clear();
    finishing_ = false;
  }

  void tick() {
    if (!news_) return;
    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - start_).count();
    if (call_test_) {
      if (elapsed > 30000) { finish("error"); return; }
      reply(job_, "call");
      return;
    }
    // Final completion uses the actual SvxLink all-samples-flushed callback.
    if (elapsed > 2 * intro_ms_ + news_ms_ + 10000) { finish("error"); return; }
    reply(job_, elapsed < intro_ms_ ? "before_beeps" : elapsed < intro_ms_ + news_ms_ ? "news" : "after_beeps");
  }

  static bool validWav(const std::string& file, unsigned expected_ms) {
    struct stat state{};
    if (lstat(file.c_str(), &state) != 0 || !S_ISREG(state.st_mode)) return false;
    std::ifstream input(file, std::ios::binary);
    unsigned char header[44]{};
    input.read(reinterpret_cast<char*>(header), sizeof(header));
    auto u16 = [&](unsigned i) { return unsigned(header[i]) | (unsigned(header[i+1]) << 8); };
    auto u32 = [&](unsigned i) { return u16(i) | (u16(i+2) << 16); };
    if (!input || std::string(reinterpret_cast<char*>(header),4) != "RIFF" ||
        std::string(reinterpret_cast<char*>(header+8),4) != "WAVE" ||
        std::string(reinterpret_cast<char*>(header+12),4) != "fmt " || u32(16) != 16 ||
        u16(20) != 1 || u16(22) != 1 || u32(24) != INTERNAL_SAMPLE_RATE || u16(34) != 16 ||
        std::string(reinterpret_cast<char*>(header+36),4) != "data") return false;
    unsigned duration = (uint64_t(u32(40)) * 1000) / (2 * INTERNAL_SAMPLE_RATE);
    return state.st_size == 44 + u32(40) && duration > 0 &&
           duration <= 1840000 && duration + 2 >= expected_ms && expected_ms + 2 >= duration;
  }
};

extern "C" { LogicBase* construct() { return new Pi3tweLogic; } }
