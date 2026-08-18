# 6. Go-live checklist

Ten minutes, every time. The first five items are the ones that actually ruin
streams — do those even when you're in a hurry.

## The five that matter

- [ ] **Record 60 seconds and listen back.** Game audio present? Voice clearly
      louder than the game? Mic not clipping? This one check catches most
      first-stream disasters.
- [ ] **Mic is unmuted in OBS** and the bar moves when you talk.
- [ ] **The game capture shows the game**, not a black rectangle, in the OBS
      preview. Check *while the game is actually running*.
- [ ] **Do Not Disturb / Focus Assist is ON.** No notification previews on
      screen.
- [ ] **Nothing private is visible** — check every source in the preview, not
      just the game. Browser tabs, launcher profiles, your real name.

## Before you hit the button

- [ ] Stream key is entered (Settings → Stream) and the platform is right
- [ ] Stream title and category/game are set on the platform's dashboard —
      the category is how anyone browsing finds you
- [ ] Local recording is on, or the replay buffer is running
- [ ] Wired connection if you have one, and no big downloads running
- [ ] Close what you don't need. A browser with 40 tabs costs you frames
- [ ] Water within reach. Three hours is longer than you think

## Your first ten minutes, live

- [ ] Go live on the **Starting Soon** scene about five minutes early. People
      need time to arrive, and the platform needs a moment to register you as
      live.
- [ ] Open OBS's **Stats** panel (View → Stats). Watch dropped frames for the
      first minute. Anything above 0% climbing means lower your bitrate.
- [ ] Check a chat message appears in Chatterino.
- [ ] Say hello and say what you're doing, even to zero viewers. Someone who
      arrives at minute 40 hears whatever you're saying then — silence reads as
      "nothing is happening here".

## While you're live

- **Talk more than feels natural.** Narrating your thinking is the entire job.
  Silence is what makes people leave, not mistakes.
- **Greet people by name** when they say hi. It's the single highest-value
  thing you can do for retention, and it costs nothing.
- **Read chat out loud** before you answer, so viewers who missed the message
  can follow.
- **Cut to BRB for breaks.** Don't leave a dead game on screen.
- **Save clips as they happen.** Hit your replay-buffer hotkey after anything
  good. You will not find it again in a three-hour VOD.

## Ending

- [ ] Cut to the **Ending** scene and leave it up for two or three minutes.
      This is when follows happen.
- [ ] Say when you're next live. Concretely — "Thursday at 8" beats "soon".
- [ ] Raid someone if you're on Twitch. It's how streamers meet each other,
      and it's the fastest way into a community.
- [ ] Stop streaming, *then* stop recording. In that order.

## After

- [ ] Check the local recording actually saved and isn't corrupt
- [ ] Cut one clip while you still remember the good moment
- [ ] Note one thing to fix next time — one, not ten

## When something breaks mid-stream

| Symptom | Cause | Fix while live |
| --- | --- | --- |
| Dropped frames climbing | Network | Lower bitrate in Settings → Output, you can do it live |
| Encoding overload warning | CPU/GPU | Switch to 30 fps, or lower output resolution |
| Game capture goes black | Alt-tab or fullscreen switch | Cut to Just Chatting, toggle the source's visibility off and on |
| Chat says no audio | Wrong device, or muted | Check the mixer, then Properties → pick the device explicitly |
| Everything is stuttering | Something else started | Close the browser, check for a Windows update downloading |

Nobody remembers a technical problem you fixed in thirty seconds. They remember
you sitting in silence while you fixed it — so talk through it.
