import { useEffect } from "react";
import type { ReactNode } from "react";
import type { Rules } from "../api";
import { GLOSSARY, inForce, roundCount, sectionOf } from "../help/glossary";
import type { GlossaryEntry, RuleSet, SectionId } from "../help/glossary";
import { useRules } from "../help/rulesContext";

const SECTIONS: { id: SectionId; title: string; only?: RuleSet }[] = [
  { id: "goal", title: "The goal" },
  { id: "round-structure", title: "How a game runs" },
  { id: "map", title: "The map and networks" },
  { id: "terrain", title: "Terrain" },
  { id: "corporations", title: "Corporations" },
  { id: "stock-round", title: "The stock round" },
  { id: "operating-turn", title: "An operating turn" },
  { id: "revenue", title: "How revenue is earned" },
  { id: "fleets", title: "Fleets and bankruptcy", only: "fleets" },
  { id: "facilities", title: "Facilities, exits and bankruptcy", only: "facilities" },
  { id: "death-star", title: "The Death Star", only: "deathStar" },
  { id: "stock-market", title: "The stock market" },
  { id: "scoring", title: "Scoring and the end" },
  { id: "verify", title: "Checking the software" },
  { id: "glossary", title: "Glossary" },
];

const TYPE_NAMES: Record<string, string> = {
  A: "Agriculture",
  R: "Resources",
  I: "Industry",
  S: "Shipyard",
  M: "Market",
};

/**
 * The full rules, written for someone who has never played an 18xx game. Every number comes from
 * the live rules so this page cannot disagree with the engine. The last sections exist so the
 * designer can check the software against the rules by hand.
 */
export function RulesPage({ section }: { section: SectionId | null }) {
  const rules = useRules();
  useEffect(() => {
    if (section) document.getElementById(section)?.scrollIntoView();
  }, [section]);
  const cash = Object.entries(rules.startingCash)
    .map(([players, amount]) => `${players} players: ${amount}`)
    .join(", ");
  const perShare = 100 / rules.sharesPerCorporation;
  const deathStar = rules.deathStarRules;
  const facilities = inForce("facilities", rules);
  const fleets = inForce("fleets", rules);
  const rounds = roundCount(rules);
  const sections = SECTIONS.filter((s) => inForce(s.only, rules));
  const glossary: GlossaryEntry[] = Object.values(GLOSSARY).filter((entry: GlossaryEntry) => inForce(entry.only, rules));

  return (
    <div className="rules">
      <nav className="rules__toc" aria-label="Rules sections">
        <a className="rules__home" href="/">
          ← Back to 18BBY
        </a>
        <ol>
          {sections.map((s) => (
            <li key={s.id}>
              <a href={`#${s.id}`}>{s.title}</a>
            </li>
          ))}
        </ol>
      </nav>

      <article className="rules__body">
        <h1>18BBY rules</h1>
        <p className="rules__lede">
          18BBY is an <em>18xx-style</em> game: a board game about investing in companies that build a transport
          network and earn money from it. You will not run one company. You will own <strong>shares</strong> in
          several, steer the ones you lead, and try to finish richest. If you have never played one of these
          before, read the first four sections and start a game: the game explains each step as it comes.
        </p>

        <Section id="goal" title="The goal">
          <p>
            The winner is the player with the most <strong>worth</strong> when the game ends: your cash, plus every
            share you own valued at its current share price. Nothing else counts.
          </p>
          <p>
            Your cash grows two ways: <strong>dividends</strong> (corporations paying out money they earn to
            their shareholders) and <strong>trading shares</strong> (buying cheap, selling after the price rises).
            A corporation's share price rises when it pays dividends and when people want its shares, and falls
            when it holds back money or when shareholders sell.
          </p>
        </Section>

        <Section id="round-structure" title="How a game runs">
          <p>
            {deathStar ? (
              <>
                The game has up to {rounds} rounds, and ends sooner if the Death Star is finished (see The Death
                Star).
              </>
            ) : (
              <>The game has {rules.totalRounds} rounds.</>
            )}{" "}
            Each round is one <strong>stock round</strong> followed by {rules.operatingRoundsPerStockRound}{" "}
            <strong>operating rounds</strong>.
          </p>
          <ul>
            <li>
              <strong>Stock round</strong>: players take turns buying and selling shares. This is where you decide
              whose side you are on.
            </li>
            <li>
              <strong>Operating round</strong>: the corporations take turns. Each one builds on the map, earns
              revenue, and then either pays it to shareholders or keeps it. The corporation's <em>president</em>{" "}
              (the player with the biggest stake) makes those choices for it.
            </li>
          </ul>
          <p>
            Who operates when? Corporations operate from the highest share price to the lowest. A tie goes to the
            one that floated first.
          </p>
          <p className="rules__note">
            Bots take their turns automatically, so you only see the screen while it is your move.
          </p>
        </Section>

        <Section id="map" title="The map and networks">
          <p>
            The board is a field of hexagons. <strong>Planets</strong> sit on some of them; the rest are empty
            hyperspace, and some of that is hazardous (see Terrain). Planets are split into three{" "}
            <strong>regions</strong>: Core, Mid Rim and Outer Rim.
          </p>
          <h3>Planet types</h3>
          <p>Every planet has an economic type, shown as a letter on the map. A few have two.</p>
          <table className="rules__table">
            <tbody>
              {Object.entries(TYPE_NAMES).map(([letter, name]) => (
                <tr key={letter}>
                  <th>{letter}</th>
                  <td>{name}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3>Hyperspace lanes</h3>
          <p>
            An empty hex has no lanes until a corporation <strong>charts</strong> it. A charted hex has lanes
            leaving through some of its six sides (its <strong>exits</strong>). Two neighbouring hexes are
            connected only when <em>each</em> has an exit facing the other.{" "}
            {facilities ? (
              <>
                A planet never needs charting, but it has only a few exits, and a lane connects to it only through
                an exit it has claimed (see Facilities, exits and bankruptcy). Two planets never connect directly:
                traffic between them needs a charted lane.
              </>
            ) : (
              <>
                A planet is an open hub: it has every exit, never needs charting, and anything that touches it
                connects to it.
              </>
            )}
          </p>
          <h3>Service and reachability</h3>
          <p>
            A corporation starts on its <strong>homeworld</strong>. It may pass through an empty hex only if it
            has <strong>service</strong> there. A planet is <strong>reachable</strong> if the corporation can trace
            a connected path to it from its homeworld through hexes it serves. Only reachable planets earn revenue.
            Corporations share lanes freely: routes do not block each other.
          </p>
          <h3>The corporations</h3>
          <table className="rules__table">
            <thead>
              <tr>
                <th>Id</th>
                <th>Name</th>
                <th>Homeworld</th>
              </tr>
            </thead>
            <tbody>
              {rules.corporations.map((c) => (
                <tr key={c.id}>
                  <th>{c.id}</th>
                  <td>{c.name}</td>
                  <td>{c.homeworld}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <Section id="terrain" title="Terrain">
          <p>
            Each game lays out its hazards when it starts, from the game's seed, so the same seed always gives the
            same sky. About {percent(rules.asteroidFraction)} of the hexes that are not planets are{" "}
            <strong>asteroid fields</strong> and about {percent(rules.nebulaFraction)} are{" "}
            <strong>nebulae</strong>. Everything else is plain open space. Planets are never covered.
          </p>
          <h3>Asteroid fields</h3>
          <p>
            An asteroid field is impassable. It can never be charted, and no tile may have an exit facing one, so
            lanes bend around them. Asteroid fields are never placed so that they cut the planets into separate
            groups: there is always an asteroid-free path between any two planets.
          </p>
          <h3>Nebulae</h3>
          <ul>
            <li>
              <strong>Charting is dearer.</strong> Charting a nebula hex costs {rules.nebulaChartSurcharge} more than
              open space: {rules.chartCost + rules.nebulaChartSurcharge} instead of {rules.chartCost}.
            </li>
            <li>
              <strong>No third lane.</strong> A tile in a nebula keeps the two lanes it was charted with and can
              never be upgraded.
            </li>
            <li>
              <strong>Service is not dearer.</strong> Extending service onto a nebula tile somebody has already
              charted costs the usual {rules.serviceCost}.
            </li>
          </ul>
          <p className="rules__note">
            Upgrading a tile in open space costs {rules.upgradeCost}, more than the {rules.chartCost} to chart it.
          </p>
        </Section>

        <Section id="corporations" title="Corporations">
          <p>
            A corporation is a company that is not any player. It has its own <strong>treasury</strong> and is
            split into {rules.sharesPerCorporation} <strong>shares</strong> of {perShare}% each. At the start, all
            of them are in the <strong>IPO</strong> (not yet sold).
          </p>
          <h3>Starting one</h3>
          <p>
            During a stock round a player can <strong>start</strong> a corporation by buying its president's
            certificate ({rules.presidentShareSize} shares, {rules.presidentShareSize * perShare}%). At the same
            moment they choose its <strong>par price</strong> from {rules.parPrices.join(", ")}. The president's
            certificate costs {rules.presidentShareSize} × par. Par is a bet: a higher par means a more
            expensive start but a bigger treasury later.
          </p>
          <h3>Floating</h3>
          <p>
            A started corporation does nothing until {rules.floatThresholdShares} of its{" "}
            {rules.sharesPerCorporation} shares have been sold out of the IPO. It then <strong>floats</strong>:
            the bank gives it {rules.floatCapitalShares} × par as its treasury, and from the next operating round
            it takes turns. Money you paid for IPO shares goes to the bank, not to the corporation.
          </p>
          <h3>The president</h3>
          <p>
            The president is the player holding the most shares in the corporation (at least{" "}
            {rules.presidentShareSize * perShare}%). If another player ends up holding strictly more, the
            presidency passes to them at once. The president cannot sell below the president's share unless
            another player holds enough to take over.
          </p>
        </Section>

        <Section id="stock-round" title="The stock round">
          <p>
            Players act in <strong>priority</strong> order, going around the table. On your turn you take{" "}
            <strong>one action</strong>: buy one share, sell shares of one corporation, or pass. Then it is the
            next player's turn, and you can act again when it comes back around. The round ends when every player
            passes in a row. Priority for the next round goes to the player after whoever last bought or sold.
          </p>
          <h3>Buying</h3>
          <ul>
            <li>
              From the <strong>IPO</strong>: at the corporation's par price. (To start an unstarted corporation,
              choose a par.)
            </li>
            <li>
              From the <strong>pool</strong>: at the corporation's current share price.
            </li>
            <li>You cannot buy a corporation whose shares you sold this round.</li>
          </ul>
          <h3>Selling</h3>
          <ul>
            <li>You sell to the pool at the current share price and receive that much from the bank.</li>
            <li>
              There are <strong>no sales in the first stock round</strong>.
            </li>
            <li>
              The pool can hold at most {rules.sharesPerCorporation / 2} shares of one corporation, so you cannot
              sell past that.
            </li>
            <li>Each share sold pushes the share price down one row (see the stock market).</li>
          </ul>
          <h3>Limits</h3>
          <ul>
            <li>
              At most {rules.maxHoldingShares} shares ({rules.maxHoldingShares * perShare}%) of any one
              corporation.
            </li>
            <li>
              At most {rules.certificateLimit} certificates in total. A president's certificate counts as one.
            </li>
          </ul>
          <h3>Starting cash</h3>
          <p>{cash}.</p>
        </Section>

        <Section id="operating-turn" title="An operating turn">
          <p>
            Each floated corporation does these {deathStar ? "four" : "three"} things, in order. Its president makes
            the choices.
          </p>
          <h3>1. Network actions</h3>
          <p>
            Up to <strong>{rules.networkActionsPerTurn}</strong> actions, paid from the corporation's treasury.
            You can stop early. The options:
          </p>
          <table className="rules__table">
            <thead>
              <tr>
                <th>Action</th>
                <th>Cost</th>
                <th>What it does</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th>Chart</th>
                <td className="num">{rules.chartCost}</td>
                <td>
                  Pick an empty hex next to your network and choose any two of its six sides as lanes. You get
                  service there automatically. A nebula costs {rules.nebulaChartSurcharge} more, and an asteroid
                  field cannot be charted at all (see Terrain).
                </td>
              </tr>
              <tr>
                <th>Upgrade</th>
                <td className="num">{rules.upgradeCost}</td>
                <td>
                  On a charted two-lane hex where you have service, add a third lane. Existing lanes stay. Tiles in
                  a nebula cannot be upgraded.
                </td>
              </tr>
              <tr>
                <th>Service</th>
                <td className="num">{rules.serviceCost}</td>
                <td>
                  Extend your corporation onto a hex that is already charted, next to your network, so you can
                  pass through it. The price is the same in a nebula.
                </td>
              </tr>
            </tbody>
          </table>
          <p>
            All three need the hex to connect to the network you can already reach. A corporation that cannot
            afford an action is not offered it.
          </p>
          {fleets && (
            <>
              <h3>2. Buy fleets</h3>
              <p>
                Buy fleets from the shared supply, one at a time, at the price shown, up to{" "}
                {rules.deathStar.fleetLimit}. A corporation must end this step owning at least one fleet. Buying a
                fleet does not use a network action. See Fleets and bankruptcy.
              </p>
            </>
          )}
          {facilities && (
            <>
              <h3>2. Build facilities</h3>
              <p>
                Build facilities, one at a time, at the price shown, up to {rules.deathStar.fleetLimit} owned. Each
                one goes on a planet and gives it a new exit. A corporation must end this step owning at least one
                facility. Building does not use a network action. See Facilities, exits and bankruptcy.
              </p>
            </>
          )}
          <h3>{deathStar ? "3" : "2"}. Revenue</h3>
          <p>
            The game computes the corporation's revenue for you and picks the best pairing of planets (see the next
            section). You do not choose routes.
            {deathStar && ` It uses at most one pair per ${facilities ? "facility" : "fleet"} the corporation owns.`}
          </p>
          <h3>{deathStar ? "4" : "3"}. Pay or withhold</h3>
          <ul>
            <li>
              <strong>Pay dividends</strong>: the revenue is split into {rules.sharesPerCorporation} per-share
              amounts, rounded down. Every share <em>a player owns</em> pays its owner that amount. Shares in the
              IPO or the pool pay nobody; that money, and the rounding remainder, stay with the bank. The share
              price moves right.
            </li>
            <li>
              <strong>Withhold</strong>: all the revenue goes into the corporation's treasury. Shareholders get
              nothing, and the share price moves left one column. A turn that earned nothing counts as a
              withhold.
            </li>
          </ul>
          <p>
            Paying keeps shareholders and the share price happy now; withholding funds more track, which can earn
            more later. That tension is the core of the game.
          </p>
        </Section>

        <Section id="revenue" title="How revenue is earned">
          <p>
            Revenue comes from <strong>pairs</strong> of reachable planets. A planet can be in at most one pair per
            corporation per operating turn. The game finds the set of pairs with the highest total.
          </p>
          <h3>Trade pairs</h3>
          <p>
            Two planets whose types fit together as a supply chain earn <strong>{rules.typedPairValue}</strong>:
          </p>
          <ul>
            {rules.typedPairs.map(([a, b]) => (
              <li key={`${a}${b}`}>
                {TYPE_NAMES[a]} ↔ {TYPE_NAMES[b]}
              </li>
            ))}
          </ul>
          <h3>Regional bonus</h3>
          <p>
            A trade pair with one end in the {rules.regionalBonusRegions[0]} and the other in the{" "}
            {rules.regionalBonusRegions[1]} earns <strong>+{rules.regionalBonus}</strong>, so{" "}
            {rules.typedPairValue + rules.regionalBonus} in total.
          </p>
          <h3>Basic routes</h3>
          <p>
            After the best trade pairs are chosen, any two remaining reachable planets can pair up for{" "}
            <strong>{rules.basicRouteValue}</strong>. Basic routes never get the regional bonus.
          </p>
          <h3>Two-type planets</h3>
          <p>
            Some planets have two types (for example Industry and Shipyard). That gives flexibility, not extra
            income: the planet still appears in only one pair, and the game uses whichever type scores best.
          </p>
          <h3>Worked example</h3>
          <p>
            A corporation reaches four planets: a Core Shipyard, an Outer Rim Industry world, a Core Market, and an
            Outer Rim Agriculture world. The best pairing is Industry↔Shipyard (Outer Rim to Core: {rules.typedPairValue}{" "}
            + {rules.regionalBonus} = {rules.typedPairValue + rules.regionalBonus}) and Agriculture↔Market (Outer Rim
            to Core: {rules.typedPairValue + rules.regionalBonus}), total{" "}
            <strong>{2 * (rules.typedPairValue + rules.regionalBonus)}</strong>. With a share count of{" "}
            {rules.sharesPerCorporation}, that is {Math.floor((2 * (rules.typedPairValue + rules.regionalBonus)) / rules.sharesPerCorporation)}{" "}
            per share.
          </p>
        </Section>

        {facilities && <FacilitiesSection rules={rules} />}

        {fleets && (
          <Section id="fleets" title="Fleets and bankruptcy">
            <p>
              <strong>One fleet runs one pair.</strong> A corporation's revenue is the best set of pairs that uses no
              more pairs than it owns fleets; contract pairs need fleets too. A network with five good pairs and three
              fleets earns from its best three.
            </p>
            <h3>The shared supply</h3>
            <p>
              Every corporation buys from one supply, and the price rises when a tier sells out. Every fleet is the
              same whatever it cost: Imperial transit licensing gets dearer, the ships do not get better.
            </p>
            <table className="rules__table">
              <thead>
                <tr>
                  <th>Fleets</th>
                  <th>Price each</th>
                </tr>
              </thead>
              <tbody>
                {rules.deathStar.fleetTiers.map((tier, i) => (
                  <tr key={i}>
                    <th>{tier.count === "unlimited" ? "then any number" : `next ${tier.count}`}</th>
                    <td className="num">{tier.price}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul>
              <li>At most {rules.deathStar.fleetLimit} fleets per corporation.</li>
              <li>Fleets cannot be sold, traded or discarded.</li>
              <li>Each fleet costs the price at the moment you buy it, so buying two can cross into a dearer tier.</li>
              <li>A corporation must own at least one fleet when it finishes its fleet step.</li>
            </ul>
            <h3>Bankruptcy</h3>
            <p>
              A corporation that reaches its fleet step with <strong>no fleet</strong> and too little in its treasury
              to buy one at the current price is <strong>bankrupt</strong>. It closes for good: its shares leave the
              game and are worth nothing to anyone (nobody pays from their own cash), its treasury goes to the bank,
              and it never operates again. Its charted tiles stay on the board for everyone else. A corporation that
              has just floated can always afford its first fleet; the danger comes after a seizure.
            </p>
          </Section>
        )}

        {deathStar && (
          <Section id="death-star" title="The Death Star">
            <p>
              The Empire is building a battle station, and the corporations are its contractors. The construction
              site is a planet-like hub tagged <strong>{rules.deathStar.siteTag}</strong> (Imperial Works).{" "}
              {facilities
                ? "Unlike a planet it has every exit and holds no facilities. It needs no charting, and networks may pass through it."
                : "Like any planet it has every exit, needs no charting, and networks may pass through it."}
            </p>
            <h3>Contracts</h3>
            <p>
              The site paired with a planet of type{" "}
              {orList(rules.deathStar.contractPartnerTags.map((t) => TYPE_NAMES[t] ?? t))} is a{" "}
              <strong>contract pair</strong>. It scores the current stage's contract value, never the
              regional bonus, and the revenue matching picks it like any other pair: a president cannot refuse a
              contract the best matching uses. The site can also be half of a basic route.
            </p>
            <h3>The track</h3>
            <p>
              Each contract pair a corporation scores puts one cube on the Death Star track, paid or withheld. The
              Empire adds {rules.deathStar.empireCubesPerStockRound} at the end of every stock round. Every{" "}
              {rules.deathStar.cubesPerStage} cubes fill a stage; extra cubes carry over. A stage's result applies at
              the end of the round in which it fills, and contracts keep paying that stage's value until then.
            </p>
            <table className="rules__table">
              <thead>
                <tr>
                  <th>Stage</th>
                  <th>Contract value while building it</th>
                  <th>When it fills</th>
                </tr>
              </thead>
              <tbody>
                {rules.deathStar.stages.map((stage, i) => (
                  <tr key={stage.name}>
                    <th>
                      {i + 1}. {stage.name}
                    </th>
                    <td className="num">{stage.value}</td>
                    <td>{STAGE_RESULT_RULES[stage.result](rules)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <h3>The two sites</h3>
            <p>
              Both sites are placed with the terrain when the game starts and are shown from the start: the first in
              the {rules.deathStar.siteRegions[0]}, the second in the {rules.deathStar.siteRegions[1]}, each at least{" "}
              {rules.deathStar.minHomeworldDistance} hexes from every homeworld. The second is{" "}
              <strong>reserved</strong> until the site moves there: it cannot be charted, but tiles may point at it,
              so you can build toward it in advance. A site never connects straight to a neighbouring planet: as
              between any two planets, traffic needs a charted lane.
            </p>
            <p>
              When a site hex becomes empty space, tiles pointing into it stay, and any network that ran through the
              site is cut there.
            </p>
          </Section>
        )}

        <Section id="stock-market" title="The stock market">
          <p>
            Every started corporation has a marker on the grid below. Its cell shows the corporation's{" "}
            <strong>share price</strong>. The grid has {rules.stockMarket.length} rows. Moving up a row is worth
            about one column to the right. Lower rows end sooner, so a corporation that has been pushed down has
            less room to grow.
          </p>
          <MarketTable rules={rules} />
          <p className="rules__note">Highlighted cells are the par prices a president can start a corporation at.</p>
          <h3>What moves the marker</h3>
          <table className="rules__table">
            <thead>
              <tr>
                <th>Event</th>
                <th>Move</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th>Pay dividends, revenue ≥ {rules.payoutStepFractions[0]} × price</th>
                <td>right 1 column</td>
              </tr>
              <tr>
                <th>Pay dividends, revenue ≥ {rules.payoutStepFractions[1]} × price</th>
                <td>right 2 columns</td>
              </tr>
              <tr>
                <th>Pay dividends, revenue below {rules.payoutStepFractions[0]} × price</th>
                <td>no move</td>
              </tr>
              <tr>
                <th>Withhold (including zero revenue)</th>
                <td>left 1 column</td>
              </tr>
              <tr>
                <th>A share is sold to the pool</th>
                <td>down 1 row per share sold</td>
              </tr>
              <tr>
                <th>Sold out at the end of a stock round</th>
                <td>up 1 row</td>
              </tr>
            </tbody>
          </table>
          <p>
            A corporation is <strong>sold out</strong> when it has no shares left in the IPO or the pool. At the
            edge of the grid a move that cannot happen turns into a different one: a right move off the end of a
            row goes up a row instead, and a left move off the left edge goes down a row. A sale cannot push a
            marker below the bottom row, or past the end of a shorter row.
          </p>
        </Section>

        <Section id="scoring" title="Scoring and the end">
          {deathStar ? (
            <p>
              The game ends after the set of operating rounds in which the Death Star launches (the Battle of
              Yavin), or after round {rounds}'s last operating round if it never does. Each player's score is their
              cash plus each share they own at its final share price; shares of a bankrupt corporation are worth
              nothing. Highest wins.
            </p>
          ) : (
            <p>
              After round {rules.totalRounds}'s last operating round the game ends. Each player's score is their
              cash plus each share they own at its final share price. Highest wins. (The fixed round count is a
              stand-in; a story-driven ending is planned.)
            </p>
          )}
        </Section>

        <Section id="verify" title="Checking the software">
          <p>
            This section is for checking that the game does what the rules say. Each line is something you can set
            up and observe. If one disagrees with what you see, that is a bug in the software (or in this page).
            The Undo button (U) lets you retry a step.
          </p>
          <h3>Setup</h3>
          <Check>
            Start a game. Each player's <b>Cash</b> equals the starting cash for the player count: {cash}.
          </Check>
          <Check>
            Every corporation is <b>unstarted</b> with price "—". There are {rules.corporations.length}{" "}
            corporations, each with the homeworld in the table above.
          </Check>
          <h3>Stock round</h3>
          <Check>
            First stock round: no <b>Sell</b> control appears for any corporation.
          </Check>
          <Check>
            Start a corporation at par <i>P</i>: your cash falls by {rules.presidentShareSize} × <i>P</i>; its
            status becomes <b>parred</b>; its price and par both read <i>P</i>; you are <b>President</b>; IPO shows{" "}
            {rules.sharesPerCorporation - rules.presidentShareSize}; its marker is in the par column of the
            market on the cell showing <i>P</i>.
          </Check>
          <Check>
            Only par prices {rules.parPrices.join(", ")} are offered, and only those you can afford at{" "}
            {rules.presidentShareSize} × par.
          </Check>
          <Check>
            Buy IPO shares until {rules.floatThresholdShares} total are sold (counting the president's{" "}
            {rules.presidentShareSize}): the status flips to <b>floated</b> and Treasury equals{" "}
            {rules.floatCapitalShares} × par. Not before.
          </Check>
          <Check>
            Buying an IPO share costs exactly par and the pool buy costs the current price; your cash drops by that
            amount.
          </Check>
          <Check>
            You are never offered a buy once you hold {rules.maxHoldingShares} shares of one corporation, nor once
            you hold {rules.certificateLimit} certificates. A president's share counts as one certificate.
          </Check>
          <Check>
            In a later stock round, sell {"n"} shares: cash rises by {"n"} × price, the pool count rises by {"n"},
            the marker drops {"n"} rows, and you cannot buy that corporation again this round. Selling is not
            offered once the pool would pass {rules.sharesPerCorporation / 2}.
          </Check>
          <Check>
            If another player's holding passes the president's, the President label moves at once.
          </Check>
          <Check>
            At the end of a stock round, a started corporation with IPO 0 and pool 0 moves up one row (the log says
            "is sold out").
          </Check>
          <h3>Operating round</h3>
          <Check>
            Corporations operate from highest price to lowest; ties go to whichever floated first (the Order column
            in the Corporations panel).
          </Check>
          <Check>
            Each network action reduces the treasury by its cost ({rules.chartCost} chart, or{" "}
            {rules.chartCost + rules.nebulaChartSurcharge} in a nebula; {rules.upgradeCost} upgrade;{" "}
            {rules.serviceCost} service), at most {rules.networkActionsPerTurn} per turn, and no action is offered
            you cannot afford.
          </Check>
          <Check>
            Asteroid fields (dark, with rocks) are never highlighted and never offered any action. No chart or
            upgrade you are offered adds an exit facing an asteroid field.
          </Check>
          <Check>
            Nebulae (purple haze): a chart option there shows {rules.chartCost + rules.nebulaChartSurcharge} and is
            labelled nebula; a charted nebula tile is never offered an upgrade; extending service onto one costs{" "}
            {rules.serviceCost}.
          </Check>
          <Check>
            Chart: pick two exits on an uncharted hex touching your network, and the corporation immediately has
            service there. Upgrade: a charted hex gains exactly one exit and keeps its old two. Service: only on an
            already-charted hex next to your network.
          </Check>
          <Check>
            A corporation's reachable planets include its homeworld, and grow only when a path is connected with
            matching exits on both sides.
          </Check>
          <Check>
            Revenue: each listed pair is {rules.typedPairValue} (typed), {rules.typedPairValue + rules.regionalBonus}{" "}
            (typed, Core↔Outer Rim) or {rules.basicRouteValue} (basic). No planet appears in two pairs. The total
            is the sum.
          </Check>
          <Check>
            Pay: each player's cash rises by ⌊revenue ÷ {rules.sharesPerCorporation}⌋ × shares held. Nothing goes to
            the IPO or pool shares.
          </Check>
          <Check>
            Withhold: the treasury rises by the full revenue and no player gains cash.
          </Check>
          <Check>
            Price after a pay: unchanged if revenue is under {rules.payoutStepFractions[0]} × price, one column
            right at {rules.payoutStepFractions[0]} × price or more, two columns right at{" "}
            {rules.payoutStepFractions[1]} × price or more. After a withhold: one column left. The button shows the
            price it will lead to.
          </Check>
          {facilities && <FacilityChecks rules={rules} />}
          {fleets && (
            <>
              <h3>Fleets and the Death Star</h3>
              <Check>
                The fleet price on the Death Star bar starts at {rules.deathStar.fleetTiers[0].price} and rises to the
                next tier's price once that tier's fleets are sold. Buying a fleet takes exactly that price from the
                treasury.
              </Check>
              <Check>
                A corporation never runs more pairs than it owns fleets: the dividend view says how many pairs run.
                It is never offered a fleet past {rules.deathStar.fleetLimit}, nor Finish while it owns none.
              </Check>
              <Check>
                Each contract pair scored adds one cube to the track, whether paid or withheld, and the Empire adds{" "}
                {rules.deathStar.empireCubesPerStockRound} at the end of each stock round.
              </Check>
              <Check>
                When a seizure stage fills, at the end of that round every corporation with a fleet has one fewer;
                when the site-move stage fills, the site jumps to the dashed future site and the old hex is empty
                space.
              </Check>
              <Check>
                A corporation with no fleet whose treasury is below the fleet price at its fleet step is shown as
                closed, its shares disappear from every player, and its tiles stay on the map.
              </Check>
            </>
          )}
          <h3>End of game</h3>
          <Check>
            {deathStar
              ? `The game stops after the round in which the station launches, or after round ${rounds}.`
              : `The game stops after round ${rules.totalRounds}.`}{" "}
            Final worth is cash plus shares × final price, and the Players table agrees with the Game over screen.
          </Check>
        </Section>

        <Section id="glossary" title="Glossary">
          <dl className="rules__glossary">
            {glossary
              .slice()
              .sort((a, b) => a.term.localeCompare(b.term))
              .map((entry) => (
                <div key={entry.term}>
                  <dt>{entry.term}</dt>
                  <dd>
                    {entry.summary(rules)}{" "}
                    <a href={`#${sectionOf(entry, rules)}`}>
                      See: {SECTIONS.find((s) => s.id === sectionOf(entry, rules))?.title}
                    </a>
                  </dd>
                </div>
              ))}
          </dl>
        </Section>
      </article>
    </div>
  );
}

const STAGE_RESULT_RULES: Record<Rules["deathStar"]["stages"][number]["result"], (rules: Rules) => ReactNode> = {
  seizure: (rules) =>
    rules.facilityRules ? (
      <>
        <strong>Seizure:</strong> the Empire takes over one facility from every corporation that has one: the one
        nearest the construction site (the most recently built on a tie). It becomes Imperial: it stays on its
        planet, fills its slot and keeps its exit, but runs pairs for nobody.
      </>
    ) : (
      <>
        <strong>Seizure:</strong> every corporation with a fleet loses one. Seized fleets leave the game.
      </>
    ),
  move: (rules) => (
    <>
      <strong>The site moves</strong> to its reserved hex in the {rules.deathStar.siteRegions[1]}; the old hex
      becomes empty, uncharted space.
    </>
  ),
  completion: () => (
    <>
      <strong>The station launches:</strong> the site leaves the board, the current round's operating rounds
      finish, and the game ends.
    </>
  ),
};

/** "A, B or C". */
function orList(items: string[]): string {
  return items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} or ${items[items.length - 1]}`;
}

function percent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}

function Section({ id, title, children }: { id: SectionId; title: string; children: ReactNode }) {
  return (
    <section id={id} className="rules__section">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function Check({ children }: { children: ReactNode }) {
  return (
    <label className="rules__check">
      <input type="checkbox" />
      <span>{children}</span>
    </label>
  );
}

function MarketTable({ rules }: { rules: Rules }) {
  const parSet = new Set(rules.parPrices);
  return (
    <div className="rules__market-wrap">
      <table className="rules__market">
        <tbody>
          {rules.stockMarket.map((row, r) => (
            <tr key={r}>
              {row.map((price, c) => (
                <td
                  key={c}
                  className={`num${c === rules.parColumn && parSet.has(price) ? " rules__market-par" : ""}`}
                >
                  {price}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The facility rules in full: planet exits, building facilities, their price and bankruptcy. */
function FacilitiesSection({ rules }: { rules: Rules }) {
  const { baseExits, perPlanet } = rules.facilities;
  return (
    <Section id="facilities" title="Facilities, exits and bankruptcy">
      <p>
        <strong>One facility runs one pair.</strong> A corporation's revenue is the best set of pairs that uses no more
        pairs than it owns facilities, wherever they are; contract pairs need one too. Facilities also open planets up:
        each one gives its planet another exit, which any corporation's lanes can use.
      </p>
      <h3>Planet exits</h3>
      <ul>
        <li>
          A planet has {baseExits} {baseExits === 1 ? "exit" : "exits"}, plus one per facility on it. It holds at most{" "}
          {perPlanet} facilities, corporate or Imperial, so it has at most {baseExits + perPlanet} exits. The Death Star
          site has all six.
        </li>
        <li>
          An exit has no direction until a lane <strong>claims</strong> it. The first tile charted (or upgraded) with an
          exit facing the planet takes one of its open exits: first come, first served. A planet connects only through
          its claimed exits. On the map, each open exit is a small ring above the planet.
        </li>
        <li>
          You may still chart a tile with an exit facing a planet that has no open exit. That lane{" "}
          <strong>dangles</strong> (a red bar on the map): it does not connect there until a facility gives it an exit.
          The tile must still join your network through another of its exits.
        </li>
        <li>
          With one exit a planet is a dead end. A network passes through a planet only in through one claimed exit and
          out through another.
        </li>
      </ul>
      <h3>Building facilities</h3>
      <p>
        After its network actions a corporation may build facilities, one at a time, without using a network action. It
        may build on a planet with a free slot that its network reaches, that one of its own lanes points at, or that
        already holds one of its facilities. Never on the Death Star site.
      </p>
      <p>
        The builder decides where the new exit goes: to a lane that dangles at that planet (anybody's), connecting it,
        or left open for the next tile charted toward the planet. Connecting a dangling lane can extend your network,
        or a rival's.
      </p>
      <h3>Price and limits</h3>
      <p>Every facility comes from one supply shared by all corporations, and the price rises when a tier sells out.</p>
      <table className="rules__table">
        <thead>
          <tr>
            <th>Facilities</th>
            <th>Price each</th>
          </tr>
        </thead>
        <tbody>
          {rules.deathStar.fleetTiers.map((tier, i) => (
            <tr key={i}>
              <th>{tier.count === "unlimited" ? "then any number" : `next ${tier.count}`}</th>
              <td className="num">{tier.price}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul>
        <li>At most {rules.deathStar.fleetLimit} facilities per corporation.</li>
        <li>
          A corporation floats with one free facility on its homeworld, outside the supply, so its homeworld starts with
          two open exits. Until it floats, one slot there is kept for it.
        </li>
        <li>Each facility costs the price at the moment it is built, so building two can cross into a dearer tier.</li>
        <li>A corporation must own at least one facility when it finishes its facility step.</li>
        <li>Facilities cannot be sold or moved.</li>
      </ul>
      <h3>Bankruptcy</h3>
      <p>
        A corporation that reaches its facility step owning <strong>no facility</strong>, and cannot build one (too little
        money, or no planet it may build on), is <strong>bankrupt</strong>. It closes for good: its shares leave the game
        and are worth nothing to anyone (nobody pays from their own cash), its treasury goes to the bank, and it never
        operates again. Its tiles stay on the board for everyone else. The danger comes after a seizure takes its last
        facility.
      </p>
    </Section>
  );
}

/** Things to check by hand under the facility rules. */
function FacilityChecks({ rules }: { rules: Rules }) {
  return (
    <>
      <h3>Facilities and the Death Star</h3>
      <Check>
        A corporation that floats gets a facility on its homeworld for free: its marker appears beside the planet and
        the planet shows two open rings.
      </Check>
      <Check>
        The facility price on the Death Star bar starts at {rules.deathStar.fleetTiers[0].price} and rises to the next
        tier's price once that tier is sold. Building a facility takes exactly that price from the treasury.
      </Check>
      <Check>
        Charting a tile with an exit toward a planet that shows an open ring claims it: the ring goes and the lane runs
        into the planet. With no ring left, the new lane ends in a red bar and does not connect.
      </Check>
      <Check>
        A facility adds one exit to its planet: a new ring, or a lane into the planet if you gave it to a dangling lane.
        No planet holds more than {rules.facilities.perPlanet}, no corporation owns more than{" "}
        {rules.deathStar.fleetLimit}, and Finish is not offered while it owns none.
      </Check>
      <Check>A corporation never runs more pairs than it owns facilities: the dividend view says how many pairs run.</Check>
      <Check>
        Each contract pair scored adds one cube to the track, whether paid or withheld, and the Empire adds{" "}
        {rules.deathStar.empireCubesPerStockRound} at the end of each stock round.
      </Check>
      <Check>
        When a seizure stage fills, at the end of that round each corporation with a facility loses the one nearest the
        site: its marker becomes the purple Imperial diamond, and the planet keeps the exit. When the site-move stage
        fills, the site jumps to the dashed future site and the old hex is empty space.
      </Check>
      <Check>
        A corporation with no facility at its facility step that cannot build one is shown as closed, its shares
        disappear from every player, and its tiles stay on the map.
      </Check>
    </>
  );
}
