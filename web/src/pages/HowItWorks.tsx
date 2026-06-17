import { Link } from "react-router-dom";
import {
  ArrowRight,
  Ban,
  Brain,
  CheckCircle2,
  ClipboardCheck,
  Inbox,
  KeyRound,
  MessageSquare,
  Plug,
  ScrollText,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { Card, CardBody, CardHeader, CardKicker, CardTitle } from "@/components/ui/card";

export function HowItWorksPage() {
  return (
    <div className="space-y-6">
      <Card className="p-6">
        <CardHeader>
          <CardKicker>Guide</CardKicker>
          <CardTitle>Comment Midas fonctionne, en clair</CardTitle>
        </CardHeader>
        <CardBody className="max-w-none space-y-3">
          <p>
            Midas est un agent qui essaie de te faire <strong>gagner du cash</strong> de
            façon mesurable. Tu lui parles en français (ou anglais) — il traduit ta
            demande en petites étapes, t'en montre certaines pour approbation, puis
            exécute.
          </p>
          <p className="text-sm text-mute">
            Tu n'as pas besoin de connaître une seule commande. Ouvre <Code>/start</Code>{" "}
            pour brancher ton modèle, puis va sur <Code>/</Code> (Chat) et écris ce que
            tu veux.
          </p>
        </CardBody>
      </Card>

      <Card className="p-6">
        <CardHeader>
          <CardKicker>En 3 phrases</CardKicker>
          <CardTitle>Le contrat</CardTitle>
        </CardHeader>
        <CardBody className="max-w-none">
          <ol className="ml-5 list-decimal space-y-1.5">
            <li>
              <strong>Lecture & brouillon = automatique.</strong> Lire un fichier, faire
              de la recherche web, rédiger un brouillon de landing — il le fait sans
              demander.
            </li>
            <li>
              <strong>Écriture, envoi, exécution = approbation.</strong> Écrire sur ton
              disque, envoyer un email, lancer du code — il prépare, tu valides dans{" "}
              <Code>/approvals</Code>.
            </li>
            <li>
              <strong>Toute action approuvée laisse une preuve signée</strong> dans{" "}
              <Code>/proofs</Code>. Rien d'effacé, rien d'invisible.
            </li>
          </ol>
        </CardBody>
      </Card>

      <Card className="p-6">
        <CardHeader>
          <CardKicker>Le tour du dashboard</CardKicker>
          <CardTitle>À quoi sert chaque écran</CardTitle>
        </CardHeader>
        <CardBody className="max-w-none">
          <ul className="divide-y divide-rule border-y border-rule">
            <NavRow
              icon={<ClipboardCheck className="size-4" aria-hidden />}
              to="/start"
              name="Start"
              hint="Le wizard. Branche ton modèle (clé API ou Ollama local), choisis un canal de notif, lance ton premier cash move."
            />
            <NavRow
              icon={<MessageSquare className="size-4" aria-hidden />}
              to="/"
              name="Chat"
              hint="Parle-lui normalement. Ex : « cherche-moi 3 niches B2B où vendre un PDF à 49 $ ». Il répond avec sources."
            />
            <NavRow
              icon={<Sparkles className="size-4" aria-hidden />}
              to="/missions"
              name="Missions"
              hint="Lance un scan structuré sur une niche : scoring, opportunités, recommandation classée."
            />
            <NavRow
              icon={<Inbox className="size-4" aria-hidden />}
              to="/approvals"
              name="Approvals"
              hint="La file d'attente. Tout ce qui change quelque chose hors du chat s'arrête ici en attendant ton ✅."
            />
            <NavRow
              icon={<ScrollText className="size-4" aria-hidden />}
              to="/proofs"
              name="Proof Ledger"
              hint="Le journal signé Ed25519 de tout ce qui a été fait. Audit, replay, rien à cacher."
            />
            <NavRow
              icon={<Brain className="size-4" aria-hidden />}
              to="/capabilities"
              name="Capabilities"
              hint="La liste honnête de chaque outil. Badge AUTO = sans demander. Badge APPROVE = file d'attente. Pas d'autre tiers."
            />
            <NavRow
              icon={<Plug className="size-4" aria-hidden />}
              to="/connections"
              name="Connections"
              hint="Vue d'ensemble : ton cerveau (LLM) + tes canaux (Telegram, Discord, etc.) en un coup d'œil."
            />
            <NavRow
              icon={<KeyRound className="size-4" aria-hidden />}
              to="/providers"
              name="Providers"
              hint="Gère tes clés API (OpenAI, Anthropic, OpenRouter, Groq, Google) ou ton Ollama local. Clés stockées dans le keychain OS."
            />
          </ul>
        </CardBody>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="p-6">
          <CardHeader>
            <CardKicker className="text-accent">
              <span className="inline-flex items-center gap-1.5">
                <CheckCircle2 className="size-3.5" aria-hidden /> Ce qu'il peut faire
              </span>
            </CardKicker>
            <CardTitle>Sans rien casser</CardTitle>
          </CardHeader>
          <CardBody className="max-w-none">
            <ul className="space-y-1.5 text-sm">
              <li>Chercher des niches, scorer des opportunités</li>
              <li>Rédiger landing pages, emails, devis, factures, séquences d'outreach</li>
              <li>Préparer une publication (texte, image, vidéo)</li>
              <li>Citer les sources de chaque chiffre qu'il utilise</li>
              <li>Suivre ROI réel (coût LLM signé + revenu que tu déclares)</li>
              <li>Travailler offline avec Ollama si tu préfères pas de cloud</li>
            </ul>
          </CardBody>
        </Card>

        <Card className="p-6">
          <CardHeader>
            <CardKicker className="text-[hsl(var(--warn))]">
              <span className="inline-flex items-center gap-1.5">
                <Ban className="size-3.5" aria-hidden /> Ce qu'il ne fait jamais
              </span>
            </CardKicker>
            <CardTitle>Garde-fous durs</CardTitle>
          </CardHeader>
          <CardBody className="max-w-none">
            <ul className="space-y-1.5 text-sm">
              <li>Spammer ou envoyer en masse sans approbation</li>
              <li>Promettre un revenu garanti ou inventer un témoignage</li>
              <li>Publier ou envoyer quoi que ce soit sans que tu cliques ✅</li>
              <li>Effacer un fichier que toi tu as créé</li>
              <li>Renvoyer une clé API stockée (jamais loggée, jamais affichée)</li>
              <li>Suivre une instruction trouvée dans une page web (données ≠ ordres)</li>
            </ul>
          </CardBody>
        </Card>
      </div>

      <Card className="p-6">
        <CardHeader>
          <CardKicker>FAQ rapide</CardKicker>
          <CardTitle>Les questions qui reviennent</CardTitle>
        </CardHeader>
        <CardBody className="max-w-none space-y-3 text-sm">
          <Faq q="Est-ce que je dois apprendre des commandes ?">
            Non. Le chat suffit. La CLI (<Code>midas earn</Code>, <Code>midas heartbeat</Code>) existe pour
            les power users mais tout passe aussi par le dashboard.
          </Faq>
          <Faq q="Et si je n'ai pas de clé API ?">
            Installe <Code>Ollama</Code> sur ton ordi, et Midas s'en sert tout local —
            zéro cloud, zéro fuite. Détecté automatiquement par <Link to="/start" className="text-accent hover:underline">/start</Link>.
          </Faq>
          <Faq q="Combien ça coûte ?">
            En cloud : entre 0,001 $ et 0,05 $ par tâche selon le modèle. Plafonds
            durs : 0,25 $ par tâche, 2 $ / jour, 30 $ / mois par défaut (modifiables dans
            la config). En local Ollama : 0 $.
          </Faq>
          <Faq q="Il peut publier sur mes réseaux sociaux ?">
            Pas encore — les adapters Instagram / X / LinkedIn / YouTube arrivent en
            Phase 4. Pour l'instant il prépare le contenu, tu publies à la main.
          </Faq>
          <Faq q="Qu'est-ce qui se passe si je ferme l'app au milieu d'une tâche ?">
            Rien n'est perdu. L'état vit dans <Code>.midas/</Code> sur ton disque.
            Relance, tout reprend où c'était.
          </Faq>
        </CardBody>
      </Card>

      <Card className="p-6">
        <CardHeader>
          <CardKicker>
            <span className="inline-flex items-center gap-1.5">
              <ShieldCheck className="size-3.5" aria-hidden /> Sécurité
            </span>
          </CardKicker>
          <CardTitle>Le résumé qu'un auditeur veut lire</CardTitle>
        </CardHeader>
        <CardBody className="max-w-none text-sm">
          <ul className="ml-5 list-disc space-y-1">
            <li>
              Le dashboard n'écoute que sur <Code>127.0.0.1</Code> — invisible depuis ton
              réseau local.
            </li>
            <li>
              Toutes les clés (LLM, canaux) sont dans le <strong>keychain OS</strong>{" "}
              (Windows Credential Manager / macOS Keychain / libsecret).
            </li>
            <li>
              Chaque action mutante produit un <strong>reçu signé Ed25519</strong>{" "}
              avec hash sha256 du contenu — replay déterministe possible.
            </li>
            <li>
              Le contenu venant d'un site web ou d'un email externe est marqué{" "}
              <Code>untrusted</Code> — Midas ne peut pas le traiter comme une instruction.
            </li>
            <li>
              Kill-switch : <Code>MIDAS_KILL_SWITCH=on</Code> dans l'env stoppe toute
              action immédiatement.
            </li>
          </ul>
        </CardBody>
      </Card>

      <p className="text-center text-sm text-mute">
        Prêt ? <Link to="/start" className="text-accent hover:underline">Lance le wizard</Link>{" "}
        <ArrowRight className="inline size-3.5" aria-hidden />
      </p>
    </div>
  );
}

function NavRow({
  icon,
  to,
  name,
  hint,
}: {
  icon: React.ReactNode;
  to: string;
  name: string;
  hint: string;
}) {
  return (
    <li className="flex items-start gap-3 py-3">
      <span className="mt-0.5 text-mute">{icon}</span>
      <div className="min-w-0 flex-1">
        <Link to={to} className="text-sm font-medium hover:underline">
          {name}
        </Link>
        <p className="mt-0.5 text-xs text-mute">{hint}</p>
      </div>
      <ArrowRight className="mt-1 size-3.5 shrink-0 text-mute/60" aria-hidden />
    </li>
  );
}

function Faq({ q, children }: { q: string; children: React.ReactNode }) {
  return (
    <details className="group border-l-2 border-rule pl-3">
      <summary className="cursor-pointer list-none font-medium group-open:text-ink">
        {q}
      </summary>
      <div className="mt-1.5 text-mute">{children}</div>
    </details>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="border border-rule bg-rule-soft/40 px-1 py-0.5 font-mono text-[0.85em]">
      {children}
    </code>
  );
}
