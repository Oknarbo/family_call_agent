# Affordable Croatian inbound access

## Recommended route

Family phone -> Croatian geographic number -> carrier SIP -> Twilio BYOC -> existing Zvonko backend.

The family calls a normal Croatian fixed-line number at its own carrier's applicable
domestic tariff. Calls may be included in the family's plan; confirm this with that carrier.
SIP delivery avoids forwarding the call over the public telephone network to a US number.
The backend remains on Hetzner, and family members do not need an app or an always-on PC.

Twilio BYOC supports numbers hosted by another carrier. This requires carrier routing and
Twilio configuration plus an application update for the incoming number/SIP address;
buying a number alone will not make the current inbound webhook accept it.
If the carrier only offers SIP registration rather than direct routing, an intermediary
such as Asterisk may be required. Confirm this before buying, because it adds maintenance.

## Candidates to request a quote from

- DIDWW advertises Croatian numbers and local SIP trunking. Obtain the actual number,
  channel, activation and inbound-minute prices from the account/quote. Confirm individual
  eligibility, documentation, direct SIP routing and original caller-ID preservation.
- Signumtel advertises SIP services. Its published tariff dated November 1, 2024 lists
  a business tariff at EUR 4/month excluding VAT with a number and two channels. This is
  not a confirmed current quote for a private family or for the required SIP configuration;
  ask whether separate trunk/activation fees apply.

Do not pick solely on headline rental. Compare total monthly cost at expected minutes,
taxes, caller-ID preservation, minimum term and ability to connect to Twilio.

Twilio lists BYOC at $0.004/min. Add carrier rental/usage, Media Streams, STT and TTS.
A verified personal outbound caller ID does not provide local inbound routing; return
calls to that personal number still reach its original service.

## Quote request for the operator to send

I need one Croatian geographic voice number for a small private family reminder assistant.
Please confirm:

1. Can an individual subscribe, and what identity/address documentation is needed?
2. What are the total activation, monthly number/channel and inbound-minute fees, including VAT?
3. Can incoming calls route directly to a Twilio BYOC SIP URI without PSTN forwarding?
4. Will the original caller's number be preserved in E.164 format for allowlisting?
5. Which codecs, SIP authentication/IP restrictions and concurrent-call limits apply?
6. Can the same number be used for outgoing calls and return calls, and what are those rates?
7. Is there a minimum contract period or a small test allowance?

This is a draft only; no message has been sent and no number purchased.

## Implementation after a quote is accepted

Provision the number, configure the carrier and Twilio BYOC endpoints, update inbound
destination validation while retaining signed webhooks and the family allowlist, test
with synthetic SIP traffic, then make one agreed short domestic phone call.
Do not remove the existing US number until the local route works.

Sources checked September 6, 2026:
[Twilio BYOC](https://www.twilio.com/docs/voice/bring-your-own-carrier-byoc),
[Twilio rates](https://www.twilio.com/en-us/voice/pricing/hr),
[DIDWW Croatia](https://www.didww.com/services/two-way-sip-trunking/outbound-sip-trunking/local-sip-trunking/Croatia),
[Signumtel published tariff](https://signumtel.hr/wp-content/uploads/Signumtel_cjenik_01-03-2023.pdf).
