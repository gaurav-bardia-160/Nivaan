# Privacy notes

Confidential documents are high risk. This project must not accept real documents until privacy handling is designed and tested.

Important distinction:

- Backend masking means the server receives original input first.
- It can reduce what is sent to an external AI provider.
- It does not mean the document never left the user's device.
- It cannot guarantee that all personal information was removed.

Planned safeguards:

- use fake documents during development
- no real uploads in early phases
- no logging of raw user text
- mask before external AI calls
- show masked item types to the user
- show disclaimer and source/date on every answer
- consider true on-device masking later
