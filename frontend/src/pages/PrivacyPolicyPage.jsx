import React from 'react';
import { Truck, Lock, MapPin, Trash2, Eye, MessageSquare } from 'lucide-react';

const Section = ({ icon: Icon, title, children }) => (
  <section className="mb-8">
    <h2 className="text-lg font-bold text-slate-900 font-archivo flex items-center gap-2 mb-2"><Icon className="w-5 h-5 text-blue-600" />{title}</h2>
    <div className="text-sm text-slate-600 space-y-2">{children}</div>
  </section>
);

export default function PrivacyPolicyPage() {
  return (
    <div className="min-h-screen bg-slate-50 py-10 px-4" data-testid="privacy-policy-page">
      <div className="max-w-3xl mx-auto bg-white rounded-2xl shadow-[0_4px_24px_rgba(0,0,0,0.06)] p-8">
        <div className="flex items-center gap-2 mb-6">
          <div className="w-9 h-9 rounded-xl bg-blue-600 flex items-center justify-center"><Truck className="w-5 h-5 text-white" /></div>
          <span className="font-archivo font-bold text-lg text-slate-900">MediTrans Ontario</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 font-archivo mb-1">Privacy Policy</h1>
        <p className="text-xs text-slate-400 mb-8">Version 1.0 · Applies to all drivers, facilities, dispatchers, administrators and delivery recipients.</p>

        <Section icon={Eye} title="What we collect">
          <p>Account details (name, email, phone), driver credentials (licence, insurance, CVOR, TDG, vulnerable-sector check), facility business details, and delivery logistics data including recipient name, phone number and delivery address. We do not collect clinical or diagnostic information; package contents are described only by generic category (e.g. "lab sample").</p>
        </Section>
        <Section icon={Lock} title="How we protect it">
          <p>All traffic is encrypted in transit with TLS/HTTPS. Recipient personal information (name, phone, proof-of-delivery recipient details) is additionally encrypted at rest with AES-128 field-level encryption before it is written to the database. Access follows least-privilege: drivers see only the logistics fields required to complete a delivery, and full addresses and recipient details are revealed only after a job is assigned to them. Every access to and change of a delivery record is written to a tamper-evident audit log that cannot be edited or deleted.</p>
        </Section>
        <Section icon={MessageSquare} title="Consent & SMS (CASL)">
          <p>Facilities must confirm the recipient's consent to the delivery and to the handling of their personal data before booking transport. SMS delivery updates are sent only with explicit consent, every message includes "Reply STOP to opt out", and STOP requests are honored immediately and permanently.</p>
        </Section>
        <Section icon={Trash2} title="Retention & deletion">
          <p>Recipient personal information (name, phone, signature evidence) is automatically redacted after the configured retention period (default 365 days) while non-identifying delivery statistics are preserved for billing and compliance. Retention length is administrator-configurable and every purge is recorded in the audit log.</p>
        </Section>
        <Section icon={MapPin} title="Data residency">
          <p>MediTrans is configured for Canadian data residency (ca-central). Production infrastructure — database, object storage and compute — is provisioned in Canadian regions so personal information remains in Canada.</p>
        </Section>
        <p className="text-xs text-slate-400 mt-6">Questions or data-access requests: contact your facility administrator or the MediTrans platform administrator.</p>
      </div>
    </div>
  );
}
