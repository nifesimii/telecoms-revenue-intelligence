# Demonstrate the partner handoff with two logins

The presentation will show a trade partner ordering and MTN Finance issuing the
invoice, which one presenter in one browser session cannot demonstrate. The user
accepted this during the two-login design interview. It narrowly supersedes ADR
0001 by allowing demonstration logins and write routes that change only the
fictional Partner Sales simulation.

Finance and Revenue Assurance share an internal role, and each partner login is
tied to exactly one account code. Credentials come from the environment, sessions
are signed `httpOnly` cookies, and access is deny by default on the server, because
hiding navigation would not stop a partner reading another dealer's data. Missing
configuration leaves the application closed, never open.

Simulation records stay in server memory, separate from every financial evidence
source, and return to the seed on restart. This is not production identity or a
partner portal: a real pilot needs enterprise identity, audit logging, a production
datastore, and invoicing and tax sign-off, as a separate scope decision. A partner
ordering in the simulation is therefore not the partner self-service portal that stays
out of scope: it changes only fictional simulation records and reads no partner's
financial evidence.
