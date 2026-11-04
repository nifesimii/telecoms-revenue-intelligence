# Keep partner sales invoicing within a presentation simulation

MTN-to-trade-partner sales invoicing will be demonstrated with fictional data
for MTN Finance and channel leadership. The user accepted this boundary during
the module design interview: operational invoicing would turn the existing
read-only intelligence MVP into a transaction-processing product requiring a
separate scope decision. This extension does not authorize production writes,
new operational write endpoints, or partner authentication.

The presentation will connect a partner's purchases and invoices with their
Partner Commission Account. Sales invoice obligations and commission earnings,
settlements, and outstanding amounts remain separately visible. The user also
accepted excluding commission offsetting against invoices from this MVP:
invoice collection and commission settlement are independent. Existing purchase-versus-activation
evidence must not be interpreted as available stock, and simulated invoices
must not be treated as actual transaction evidence.
